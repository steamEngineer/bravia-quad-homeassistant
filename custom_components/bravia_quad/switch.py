"""Switch platform for Bravia Quad power control."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, POWER_ON, POWER_OFF
from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad switch from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]
    
    # Create entity and fetch initial state
    entity = BraviaQuadPowerSwitch(client, entry)
    await entity.async_update()  # Fetch current power state
    async_add_entities([entity])


class BraviaQuadPowerSwitch(SwitchEntity):
    """Representation of a Bravia Quad power switch."""

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Power"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_power"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for power notifications
        self._client.register_notification_callback(
            "main.power",
            self._on_power_notification
        )

    async def _on_power_notification(self, value: str) -> None:
        """Handle power state notification."""
        self._attr_is_on = value == POWER_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        success = await self._client.async_set_power(POWER_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on Bravia Quad")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        success = await self._client.async_set_power(POWER_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off Bravia Quad")

    async def async_update(self) -> None:
        """Update the switch state."""
        try:
            power_state = await self._client.async_get_power()
            self._attr_is_on = power_state == POWER_ON
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update power state: %s", err)

