"""The Bravia Quad integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.const import CONF_MAC, CONF_NAME, Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .bravia_quad_client import BraviaQuadClient
from .const import (
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DOMAIN,
    MODEL_ID_TO_NAME,
)
from .helpers import migrate_legacy_identifiers

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


@dataclass
class BraviaQuadData:
    """Runtime data for a Bravia Quad config entry."""

    tcp_client: BraviaQuadClient


_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bravia Quad from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Migrate legacy device and entity identifiers (entry_id -> unique_id format)
    migrate_legacy_identifiers(hass, entry)

    # Create client instance
    client = BraviaQuadClient(
        entry.data["host"], entry.data.get(CONF_NAME, DEFAULT_NAME)
    )

    # Test connection - raise ConfigEntryNotReady on failure
    try:
        await client.async_connect()
        await client.async_test_connection()
    except (OSError, TimeoutError) as err:
        await client.async_disconnect()
        raise ConfigEntryNotReady from err

    # Let the connection stabilize, then start the notification listener
    # so command responses are routed correctly
    await asyncio.sleep(0.2)
    await client.async_listen_for_notifications()

    # Backfill permanent identity for entries created before this version
    await _backfill_identity(hass, entry, client)

    # Register the device with identity from entry.data (permanent)
    # plus firmware version and active MAC from TCP (transient)
    await _register_device(hass, entry, client)

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

    # Store runtime data and forward entry setup to platforms
    hass.data[DOMAIN][entry.entry_id] = BraviaQuadData(tcp_client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _backfill_identity(
    hass: HomeAssistant, entry: ConfigEntry, client: BraviaQuadClient
) -> None:
    """Backfill permanent identity for entries created before this version."""
    if CONF_MODEL_ID in entry.data:
        return

    _LOGGER.info("Backfilling device identity for existing entry...")
    updates: dict[str, str] = {}

    try:
        serial = await client.async_get_serial_number()
        if serial:
            updates[CONF_SERIAL] = serial
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch serial number")

    try:
        model_type = await client.async_get_model_type()
        if model_type:
            updates[CONF_MODEL_ID] = model_type
            if CONF_MODEL not in entry.data:
                updates[CONF_MODEL] = MODEL_ID_TO_NAME.get(model_type, model_type)
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch model type")

    try:
        manufacturer = await client.async_get_manufacturer()
        if manufacturer:
            updates[CONF_MANUFACTURER] = manufacturer
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch manufacturer")

    try:
        mac = await client.async_get_mac_address()
        if mac and CONF_MAC not in entry.data:
            updates[CONF_MAC] = dr.format_mac(mac)
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch MAC address")

    if updates:
        # Migrate unique_id to serial if we got one
        new_unique_id = updates.get(CONF_SERIAL)
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, **updates},
            unique_id=new_unique_id or entry.unique_id,
        )
        _LOGGER.info("Backfilled device identity: %s", list(updates.keys()))


async def _register_device(
    hass: HomeAssistant, entry: ConfigEntry, client: BraviaQuadClient
) -> None:
    """Create or update the device registry entry."""
    # Permanent identity from entry.data (set by config flow or backfill)
    manufacturer = entry.data.get(CONF_MANUFACTURER, "Sony")
    model = entry.data.get(CONF_MODEL, DEFAULT_MODEL)
    model_id = entry.data.get(CONF_MODEL_ID)
    serial = entry.data.get(CONF_SERIAL)

    # Transient data from TCP (may change between setups)
    firmware_version: str | None = None
    try:
        firmware_version = await client.async_get_firmware_version()
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch firmware version")

    active_mac: str | None = None
    try:
        active_mac = await client.async_get_mac_address()
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch active MAC")

    # Build connections from stored MAC and active MAC
    connections: set[tuple[str, str]] = set()
    if CONF_MAC in entry.data:
        connections.add((dr.CONNECTION_NETWORK_MAC, entry.data[CONF_MAC]))
    if active_mac:
        connections.add((dr.CONNECTION_NETWORK_MAC, dr.format_mac(active_mac)))

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        connections=connections,
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        manufacturer=manufacturer,
        model=model,
        model_id=model_id,
        serial_number=serial,
        sw_version=firmware_version,
        configuration_url=f"http://{entry.data['host']}",
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if entry.entry_id in hass.data[DOMAIN]:
        data: BraviaQuadData = hass.data[DOMAIN][entry.entry_id]
        await data.tcp_client.async_disconnect()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
