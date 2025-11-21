"""Number platform for Bravia Quad volume control."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad volume number entity from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]
    
    # Create entity and fetch initial state
    entity = BraviaQuadVolumeNumber(client, entry)
    await entity.async_update()  # Fetch current volume
    async_add_entities([entity])


class BraviaQuadVolumeNumber(NumberEntity):
    """Representation of a Bravia Quad volume control."""

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the volume number entity."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Volume"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_volume"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_value = 0
        self._attr_mode = "slider"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for volume notifications
        self._client.register_notification_callback(
            "main.volumestep",
            self._on_volume_notification
        )

    async def _on_volume_notification(self, value: Any) -> None:
        """Handle volume notification."""
        try:
            volume = int(value)
            if 0 <= volume <= 100:
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
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update volume: %s", err)

