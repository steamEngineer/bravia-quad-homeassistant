"""Tests for transport mode helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.bravia_quad.const import (
    CONF_GRPC_KEYS,
    CONF_HAS_SUBWOOFER,
    CONF_SERIAL,
    CONF_TRANSPORT,
    TRANSPORT_GRPC,
)
from custom_components.bravia_quad.transport import (
    identity_from_grpc_snapshot,
    infer_subwoofer_from_grpc,
    migrate_transport_entry,
    resolve_transport,
)


def test_resolve_transport_from_entry_data() -> None:
    entry = MagicMock()
    entry.data = {CONF_TRANSPORT: TRANSPORT_GRPC}
    entry.options = {}
    assert resolve_transport(entry) == TRANSPORT_GRPC


def test_resolve_transport_legacy_use_grpc() -> None:
    entry = MagicMock()
    entry.data = {}
    entry.options = {"use_grpc": True}
    assert resolve_transport(entry) == TRANSPORT_GRPC


def test_migrate_transport_from_legacy_options() -> None:
    hass = MagicMock()
    entry = MagicMock()
    entry.data = {"host": "10.0.0.1"}
    entry.options = {"use_grpc": True, CONF_GRPC_KEYS: "{}"}
    entry.entry_id = "abc"

    migrate_transport_entry(hass, entry)

    hass.config_entries.async_update_entry.assert_called_once()
    call_kwargs = hass.config_entries.async_update_entry.call_args.kwargs
    assert call_kwargs["data"][CONF_TRANSPORT] == TRANSPORT_GRPC
    assert call_kwargs["data"][CONF_GRPC_KEYS] == "{}"


def test_identity_from_grpc_snapshot() -> None:
    info = identity_from_grpc_snapshot(
        {
            "system_setting.serial_number": "8804927",
            "system_setting.friendly_name": "Office Quads",
            "system_setting.wifi_mac_address_wired": "f8:4e:17:22:ce:25",
            "system_setting.model_name": "HT-A9M2",
            "system_setting.manufacturer": "SONY",
            "sound_setting.volume.subwoofer": 5,
        }
    )
    assert info[CONF_SERIAL] == "8804927"
    assert info[CONF_HAS_SUBWOOFER] is True


def test_infer_subwoofer_from_grpc() -> None:
    assert infer_subwoofer_from_grpc(1) is False
    assert infer_subwoofer_from_grpc(5) is True
    assert infer_subwoofer_from_grpc(-1) is True
