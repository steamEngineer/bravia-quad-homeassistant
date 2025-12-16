"""The Bravia Quad integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .bravia_quad_client import BraviaQuadClient
from .const import CONF_HAS_SUBWOOFER, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bravia Quad from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create client instance
    client = BraviaQuadClient(entry.data["host"], entry.data.get("name", "Bravia Quad"))

    # Test connection - raise ConfigEntryNotReady on failure
    try:
        await client.async_connect()
        await client.async_test_connection()
    except (OSError, TimeoutError) as err:
        await client.async_disconnect()
        raise ConfigEntryNotReady from err

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

    # Give the connection a moment to stabilize
    await asyncio.sleep(0.2)

    # Start listening for notifications before fetching state so responses are captured
    await client.async_listen_for_notifications()

    # Fetch all initial states from the device
    await client.async_fetch_all_states()

    # Detect subwoofer if not already detected (for existing entries without this data)
    if CONF_HAS_SUBWOOFER not in entry.data:
        _LOGGER.info("Detecting subwoofer for existing entry...")
        try:
            has_subwoofer = await client.async_detect_subwoofer()
        except (OSError, TimeoutError):
            _LOGGER.warning(
                "Subwoofer detection failed due to connection error, "
                "defaulting to False"
            )
            has_subwoofer = False
        # Update entry data with detection result
        new_data = {**entry.data, CONF_HAS_SUBWOOFER: has_subwoofer}
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.info("Subwoofer detection complete: %s", has_subwoofer)

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
