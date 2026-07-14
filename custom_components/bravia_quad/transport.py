"""Transport mode resolution and gRPC setup helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_GRPC_KEYS,
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    CONF_TRANSPORT,
    CONF_USE_GRPC,
    DEFAULT_NAME,
    MODEL_ID_TO_NAME,
    TRANSPORT_GRPC,
    TRANSPORT_TCP,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

GRPC_PATH_SERIAL = "system_setting.serial_number"
GRPC_PATH_FRIENDLY_NAME = "system_setting.friendly_name"
GRPC_PATH_MAC_WIRED = "system_setting.wifi_mac_address_wired"
GRPC_PATH_SUBWOOFER = "sound_setting.volume.subwoofer"
GRPC_PATH_SW_STATUS = "speaker_connection_setting.connection_status.sw"
GRPC_PATH_SW_HISTORY = "speaker_connection_setting.connection_history.sw"

_SW_LINKED = frozenset({"connected", "protected"})


def resolve_transport(entry: ConfigEntry) -> str:
    """Return active transport for a config entry."""
    transport = entry.data.get(CONF_TRANSPORT)
    if transport in (TRANSPORT_TCP, TRANSPORT_GRPC):
        return transport
    if entry.options.get(CONF_USE_GRPC):
        return TRANSPORT_GRPC
    return TRANSPORT_TCP


def grpc_keys_json(entry: ConfigEntry) -> str | None:
    """Return Sony Seeds keys JSON for gRPC transport entries."""
    keys = entry.data.get(CONF_GRPC_KEYS) or entry.options.get(CONF_GRPC_KEYS)
    if keys:
        return str(keys)
    return None


def migrate_transport_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """One-time migration from legacy use_grpc option to transport in entry.data."""
    if CONF_TRANSPORT in entry.data:
        return

    transport = TRANSPORT_GRPC if entry.options.get(CONF_USE_GRPC) else TRANSPORT_TCP
    data = dict(entry.data)
    data[CONF_TRANSPORT] = transport
    if transport == TRANSPORT_GRPC:
        keys = entry.options.get(CONF_GRPC_KEYS)
        if keys and CONF_GRPC_KEYS not in data:
            data[CONF_GRPC_KEYS] = keys

    hass.config_entries.async_update_entry(entry, data=data)
    _LOGGER.info(
        "Migrated %s to transport=%s",
        entry.data.get("host", entry.entry_id),
        transport,
    )


def _level_outside_no_sub_band(value: Any) -> bool:
    """Return True when subwoofer level is outside the no-sub {0,1,2} band."""
    if value is None:
        return False
    try:
        level = int(value)
    except (TypeError, ValueError):
        return False
    return level < 0 or level > 2


def subwoofer_currently_linked(snapshot: dict[str, Any]) -> bool:
    """Return True when connection_status.sw reports a live link."""
    return snapshot.get(GRPC_PATH_SW_STATUS) in _SW_LINKED


def detect_subwoofer_from_grpc(snapshot: dict[str, Any]) -> bool:
    """
    Detect whether a subwoofer level entity should exist.

    True when currently linked or previously paired (history). Level range is
    only a fallback when the topology path is absent from the snapshot.
    """
    if subwoofer_currently_linked(snapshot):
        return True
    if snapshot.get(GRPC_PATH_SW_HISTORY) is True:
        return True
    if GRPC_PATH_SW_STATUS not in snapshot:
        return _level_outside_no_sub_band(snapshot.get(GRPC_PATH_SUBWOOFER))
    return False


def identity_from_grpc_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build config-entry identity fields from a GetStates dict."""
    result: dict[str, Any] = {
        CONF_HAS_SUBWOOFER: detect_subwoofer_from_grpc(snapshot),
    }

    serial = snapshot.get(GRPC_PATH_SERIAL)
    if serial:
        result[CONF_SERIAL] = str(serial)

    name = snapshot.get(GRPC_PATH_FRIENDLY_NAME)
    if name:
        result[CONF_NAME] = str(name)

    mac = snapshot.get(GRPC_PATH_MAC_WIRED)
    if mac:
        result[CONF_MAC] = format_mac(str(mac))

    model_id = snapshot.get("system_setting.model_name")
    if model_id:
        text = str(model_id)
        result[CONF_MODEL_ID] = text
        result[CONF_MODEL] = MODEL_ID_TO_NAME.get(text, text)

    manufacturer = snapshot.get("system_setting.manufacturer")
    if manufacturer:
        result[CONF_MANUFACTURER] = str(manufacturer)

    if CONF_NAME not in result:
        result[CONF_NAME] = DEFAULT_NAME

    return result
