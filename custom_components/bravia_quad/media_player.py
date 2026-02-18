"""Media player platform for Bravia Quad."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)

from .const import (
    DOMAIN,
    FEATURE_INPUT,
    FEATURE_POWER,
    FEATURE_VOLUME,
    INPUT_OPTIONS,
    MAX_VOLUME,
    POWER_OFF,
    POWER_ON,
)
from .helpers import VolumeTransitionMixin, get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad media player from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BraviaQuadMediaPlayer(client, entry)])


class BraviaQuadMediaPlayer(VolumeTransitionMixin, MediaPlayerEntity):
    """Representation of a Bravia Quad soundbar as a media player."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_translation_key = "bravia_quad"
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the media player."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_media_player"
        self._attr_device_info = get_device_info(entry)
        self._attr_source_list = list(INPUT_OPTIONS)
        self._update_state_from_client()
        self._init_volume_transition()

    def _update_state_from_client(self) -> None:
        """Update local state from client cached values."""
        # Power state -> MediaPlayerState
        if self._client.power_state == POWER_ON:
            self._attr_state = MediaPlayerState.ON
        else:
            self._attr_state = MediaPlayerState.OFF

        # Volume (0-100 -> 0.0-1.0)
        self._attr_volume_level = self._client.volume / MAX_VOLUME

        # Source (use raw API value)
        self._attr_source = (
            self._client.input if self._client.input in INPUT_OPTIONS else "tv"
        )

    async def _on_power_notification(self, value: str) -> None:
        """Handle power state notification."""
        if value == POWER_ON:
            self._attr_state = MediaPlayerState.ON
        else:
            self._attr_state = MediaPlayerState.OFF
        self.async_write_ha_state()

    async def _on_volume_notification(self, value: Any) -> None:
        """Handle volume notification."""
        if self.should_suppress_volume_notification():
            return

        try:
            volume = int(value)
            if 0 <= volume <= MAX_VOLUME:
                self._attr_volume_level = volume / MAX_VOLUME
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid volume notification value: %s", value)

    async def _on_input_notification(self, value: str) -> None:
        """Handle input notification."""
        if value in INPUT_OPTIONS:
            self._attr_source = value
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Unknown input value received: %s", value)

    async def async_turn_on(self) -> None:
        """Turn the soundbar on."""
        success = await self._client.async_set_power(POWER_ON)
        if success:
            self._attr_state = MediaPlayerState.ON
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on Bravia Quad")

    async def async_turn_off(self) -> None:
        """Turn the soundbar off."""
        success = await self._client.async_set_power(POWER_OFF)
        if success:
            self._attr_state = MediaPlayerState.OFF
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off Bravia Quad")

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0.0 to 1.0)."""
        clamped = min(max(volume, 0.0), 1.0)
        target_volume = round(clamped * MAX_VOLUME)
        previous_level = self._attr_volume_level
        current_volume = round((previous_level or 0) * MAX_VOLUME)

        # Set optimistic UI state immediately for smooth slider feedback
        self._attr_volume_level = target_volume / MAX_VOLUME
        self.async_write_ha_state()

        success = await self._async_set_volume_with_transition(
            current_volume, target_volume
        )

        if not success:
            # Restore previous state since the device didn't change
            self._attr_volume_level = previous_level
            self.async_write_ha_state()
            _LOGGER.error("Failed to set volume to %d", target_volume)

    async def async_volume_up(self) -> None:
        """Volume up the soundbar."""
        current_volume = round((self._attr_volume_level or 0) * MAX_VOLUME)
        new_volume = min(current_volume + 1, MAX_VOLUME)
        success = await self._client.async_set_volume(new_volume)
        if success:
            self._attr_volume_level = new_volume / MAX_VOLUME
            self.async_write_ha_state()

    async def async_volume_down(self) -> None:
        """Volume down the soundbar."""
        current_volume = round((self._attr_volume_level or 0) * MAX_VOLUME)
        new_volume = max(current_volume - 1, 0)
        success = await self._client.async_set_volume(new_volume)
        if success:
            self._attr_volume_level = new_volume / MAX_VOLUME
            self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if source not in INPUT_OPTIONS:
            _LOGGER.error("Invalid source: %s", source)
            return

        success = await self._client.async_set_input(source)
        if success:
            self._attr_source = source
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set source to %s", source)

    async def async_added_to_hass(self) -> None:
        """Register notification callbacks when entity is added."""
        await super().async_added_to_hass()
        self._client.register_notification_callback(
            FEATURE_POWER, self._on_power_notification
        )
        self._client.register_notification_callback(
            FEATURE_VOLUME, self._on_volume_notification
        )
        self._client.register_notification_callback(
            FEATURE_INPUT, self._on_input_notification
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks and cancel any ongoing transition."""
        self._client.unregister_notification_callback(
            FEATURE_POWER, self._on_power_notification
        )
        self._client.unregister_notification_callback(
            FEATURE_VOLUME, self._on_volume_notification
        )
        self._client.unregister_notification_callback(
            FEATURE_INPUT, self._on_input_notification
        )
        self._cancel_volume_transition()
        await super().async_will_remove_from_hass()
