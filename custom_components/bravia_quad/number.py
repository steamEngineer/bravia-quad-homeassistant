"""Number platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory

from .const import (
    CONF_HAS_SUBWOOFER,
    DOMAIN,
    FEATURE_BASS_LEVEL,
    FEATURE_REAR_LEVEL,
    FEATURE_VOLUME,
    MAX_BASS_LEVEL,
    MAX_REAR_LEVEL,
    MAX_VOLUME_STEP_INTERVAL,
    MIN_BASS_LEVEL,
    MIN_REAR_LEVEL,
)
from .helpers import BraviaQuadNotificationMixin, VolumeTransitionMixin, get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

# Constants for validation ranges
MAX_VOLUME = 100


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad number entities from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]

    # Create number entities
    entities: list[NumberEntity] = [
        BraviaQuadVolumeNumber(client, entry),
        BraviaQuadRearLevelNumber(client, entry),
        BraviaQuadVolumeStepIntervalNumber(client, entry),
    ]

    # Only add bass level slider if subwoofer is detected
    if entry.data.get(CONF_HAS_SUBWOOFER, False):
        entities.append(BraviaQuadBassLevelNumber(client, entry))

    async_add_entities(entities)


class BraviaQuadVolumeNumber(
    VolumeTransitionMixin, BraviaQuadNotificationMixin, NumberEntity
):
    """Representation of a Bravia Quad volume control."""

    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_VOLUME
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "volume"
    _notification_feature = FEATURE_VOLUME

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the volume number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_volume"
        self._attr_native_value = client.volume
        self._attr_device_info = get_device_info(entry)
        self._init_volume_transition()

    async def _on_notification(self, value: Any) -> None:
        """Handle volume notification."""
        if self.should_suppress_volume_notification():
            return

        try:
            volume = int(value)
            if 0 <= volume <= MAX_VOLUME:
                self._attr_native_value = volume
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid volume notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume value."""
        target_volume = int(value)
        current_volume = int(self._attr_native_value or 0)

        # Set optimistic UI state immediately for smooth slider feedback
        self._attr_native_value = target_volume
        self.async_write_ha_state()

        success = await self._async_set_volume_with_transition(
            current_volume, target_volume
        )

        if not success:
            _LOGGER.error("Failed to set volume to %d", target_volume)

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any ongoing transition when entity is removed."""
        self._cancel_volume_transition()
        await super().async_will_remove_from_hass()

    async def async_update(self) -> None:
        """Update the volume value."""
        try:
            volume = await self._client.async_get_volume()
            self._attr_native_value = volume
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update volume")


class BraviaQuadRearLevelNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad rear level control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_REAR_LEVEL
    _attr_native_min_value = MIN_REAR_LEVEL
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "rear_level"
    _notification_feature = FEATURE_REAR_LEVEL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the rear level number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_rear_level"
        self._attr_native_value = client.rear_level
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: Any) -> None:
        """Handle rear level notification."""
        try:
            rear_level = int(value)
            if MIN_REAR_LEVEL <= rear_level <= MAX_REAR_LEVEL:
                self._attr_native_value = rear_level
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid rear level notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the rear level value."""
        rear_level = int(value)
        success = await self._client.async_set_rear_level(rear_level)
        if success:
            self._attr_native_value = rear_level
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set rear level to %d", rear_level)

    async def async_update(self) -> None:
        """Update the rear level value."""
        try:
            rear_level = await self._client.async_get_rear_level()
            self._attr_native_value = rear_level
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update rear level")


class BraviaQuadBassLevelNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad bass level control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_BASS_LEVEL
    _attr_native_min_value = MIN_BASS_LEVEL
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "bass_level"
    _notification_feature = FEATURE_BASS_LEVEL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the bass level number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_bass_level_slider"
        self._attr_native_value = client.bass_level
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: Any) -> None:
        """Handle bass level notification."""
        try:
            bass_level = int(value)
            if MIN_BASS_LEVEL <= bass_level <= MAX_BASS_LEVEL:
                self._attr_native_value = bass_level
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid bass level notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the bass level value."""
        bass_level = int(value)
        success = await self._client.async_set_bass_level(bass_level)
        if success:
            self._attr_native_value = bass_level
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set bass level to %d", bass_level)

    async def async_update(self) -> None:
        """Update the bass level value."""
        try:
            bass_level = await self._client.async_get_bass_level()
            self._attr_native_value = bass_level
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update bass level")


class BraviaQuadVolumeStepIntervalNumber(RestoreNumber):
    """Representation of a Bravia Quad volume step interval control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_max_value = MAX_VOLUME_STEP_INTERVAL
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "ms"
    _attr_translation_key = "volume_step_interval"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the volume step interval number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_volume_step_interval"
        self._attr_native_value = client.volume_step_interval
        self._attr_device_info = get_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore previous state on restart."""
        await super().async_added_to_hass()
        if (
            last_state := await self.async_get_last_number_data()
        ) is not None and last_state.native_value is not None:
            self._attr_native_value = last_state.native_value
            self._client.volume_step_interval = int(last_state.native_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume step interval."""
        self._client.volume_step_interval = int(value)
        self._attr_native_value = value
        self.async_write_ha_state()
