"""Number platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory

from .const import (
    CONF_HAS_SUBWOOFER,
    DOMAIN,
    MAX_BASS_LEVEL,
    MAX_REAR_LEVEL,
    MIN_BASS_LEVEL,
    MIN_REAR_LEVEL,
)
from .helpers import get_device_info

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
    ]

    # Only add bass level slider if subwoofer is detected
    if entry.data.get(CONF_HAS_SUBWOOFER, False):
        entities.append(BraviaQuadBassLevelNumber(client, entry))

    async_add_entities(entities)


class BraviaQuadVolumeNumber(NumberEntity):
    """Representation of a Bravia Quad volume control."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_VOLUME
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "volume"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the volume number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_volume"
        self._attr_native_value = client.volume
        self._attr_device_info = get_device_info(entry)

        # Register for volume notifications
        self._client.register_notification_callback(
            "main.volumestep", self._on_volume_notification
        )

    async def _on_volume_notification(self, value: Any) -> None:
        """Handle volume notification."""
        try:
            volume = int(value)
            if 0 <= volume <= MAX_VOLUME:
                self._attr_native_value = volume
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid volume notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume value."""
        volume = int(value)
        success = await self._client.async_set_volume(volume)
        if success:
            self._attr_native_value = volume
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set volume to %d", volume)

    async def async_update(self) -> None:
        """Update the volume value."""
        try:
            volume = await self._client.async_get_volume()
            self._attr_native_value = volume
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update volume")


class BraviaQuadRearLevelNumber(NumberEntity):
    """Representation of a Bravia Quad rear level control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_REAR_LEVEL
    _attr_native_min_value = MIN_REAR_LEVEL
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "rear_level"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the rear level number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_rear_level"
        self._attr_native_value = client.rear_level
        self._attr_device_info = get_device_info(entry)

        # Register for rear level notifications
        self._client.register_notification_callback(
            "main.rearvolumestep", self._on_rear_level_notification
        )

    async def _on_rear_level_notification(self, value: Any) -> None:
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


class BraviaQuadBassLevelNumber(NumberEntity):
    """Representation of a Bravia Quad bass level control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_BASS_LEVEL
    _attr_native_min_value = MIN_BASS_LEVEL
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "bass_level"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the bass level number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_bass_level_slider"
        self._attr_native_value = client.bass_level
        self._attr_device_info = get_device_info(entry)

        # Register for bass level notifications
        self._client.register_notification_callback(
            "main.bassstep", self._on_bass_level_notification
        )

    async def _on_bass_level_notification(self, value: Any) -> None:
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
