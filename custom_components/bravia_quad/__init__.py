"""The Bravia Quad integration."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bravia Quad from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Create client instance
    client = BraviaQuadClient(
        entry.data["host"],
        entry.data.get("name", "Bravia Quad")
    )
    
    # Test connection
    try:
        await client.async_connect()
        await client.async_test_connection()
    except Exception as err:
        _LOGGER.error("Failed to connect to Bravia Quad: %s", err)
        return False
    
    # Create device registry entry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get("name", "Bravia Quad"),
        manufacturer="Sony",
        model="Bravia Quad",
        configuration_url=f"http://{entry.data['host']}",
    )
    
    # Store client in hass.data
    hass.data[DOMAIN][entry.entry_id] = client
    
    # Start listening for notifications
    asyncio.create_task(client.async_listen_for_notifications())
    
    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if entry.entry_id in hass.data[DOMAIN]:
        client = hass.data[DOMAIN][entry.entry_id]
        await client.async_disconnect()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

