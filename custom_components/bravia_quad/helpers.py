"""Shared helpers for Bravia Quad integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_MAC
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return device info for a Bravia Quad device."""
    # Build connections set if MAC address is available
    connections: set[tuple[str, str]] = set()
    if CONF_MAC in entry.data:
        connections.add((CONNECTION_NETWORK_MAC, entry.data[CONF_MAC]))

    # Build identifiers - unique_id should always be set, but handle None
    unique_id = entry.unique_id or entry.entry_id

    return DeviceInfo(
        identifiers={(DOMAIN, unique_id)},
        connections=connections,
        name=entry.data.get("name", "Bravia Quad"),
        manufacturer="Sony",
        model="Bravia Quad",
        configuration_url=f"http://{entry.data['host']}",
    )
