"""Tests for transport mode helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_MAC

from custom_components.bravia_quad.const import (
    CONF_GRPC_KEYS,
    CONF_HAS_SUBWOOFER,
    CONF_SERIAL,
    CONF_TRANSPORT,
    TRANSPORT_GRPC,
)
from custom_components.bravia_quad.transport import (
    GRPC_PATH_MAC_WIRED,
    GRPC_PATH_MAC_WIRELESS,
    GRPC_PATH_SUBWOOFER,
    GRPC_PATH_SW_HISTORY,
    GRPC_PATH_SW_STATUS,
    detect_subwoofer_from_grpc,
    identity_from_grpc_snapshot,
    migrate_transport_entry,
    resolve_transport,
    subwoofer_currently_linked,
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
            GRPC_PATH_MAC_WIRED: "f8:4e:17:22:ce:25",
            "system_setting.model_name": "HT-A9M2",
            "system_setting.manufacturer": "SONY",
            GRPC_PATH_SW_STATUS: "connected",
            GRPC_PATH_SUBWOOFER: None,
        }
    )
    assert info[CONF_SERIAL] == "8804927"
    assert info[CONF_HAS_SUBWOOFER] is True
    assert info[CONF_MAC] == "f8:4e:17:22:ce:25"


@pytest.mark.parametrize(
    ("snapshot", "expected_mac"),
    [
        ({GRPC_PATH_MAC_WIRED: "AA:BB:CC:DD:EE:01"}, "aa:bb:cc:dd:ee:01"),
        ({GRPC_PATH_MAC_WIRELESS: "AA:BB:CC:DD:EE:02"}, "aa:bb:cc:dd:ee:02"),
        (
            {
                GRPC_PATH_MAC_WIRED: "AA:BB:CC:DD:EE:01",
                GRPC_PATH_MAC_WIRELESS: "AA:BB:CC:DD:EE:02",
            },
            "aa:bb:cc:dd:ee:01",
        ),
        ({}, None),
    ],
)
def test_identity_from_grpc_snapshot_mac_preference(
    snapshot: dict[str, object], expected_mac: str | None
) -> None:
    info = identity_from_grpc_snapshot(snapshot)
    assert info.get(CONF_MAC) == expected_mac


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({GRPC_PATH_SW_STATUS: "connected"}, True),
        ({GRPC_PATH_SW_STATUS: "protected"}, True),
        (
            {
                GRPC_PATH_SW_STATUS: "disconnected",
                GRPC_PATH_SW_HISTORY: True,
            },
            True,
        ),
        (
            {
                GRPC_PATH_SW_STATUS: "disconnected",
                GRPC_PATH_SW_HISTORY: None,
                GRPC_PATH_SUBWOOFER: 5,
            },
            False,
        ),
        (
            {
                GRPC_PATH_SW_STATUS: "disconnected",
                GRPC_PATH_SUBWOOFER: None,
            },
            False,
        ),
        ({GRPC_PATH_SUBWOOFER: 5}, True),
        ({GRPC_PATH_SUBWOOFER: 1}, False),
        ({GRPC_PATH_SUBWOOFER: -1}, True),
        ({GRPC_PATH_SUBWOOFER: None}, False),
        ({}, False),
    ],
)
def test_detect_subwoofer_from_grpc(
    snapshot: dict[str, object], expected: bool
) -> None:
    assert detect_subwoofer_from_grpc(snapshot) is expected


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({GRPC_PATH_SW_STATUS: "connected"}, True),
        ({GRPC_PATH_SW_STATUS: "protected"}, True),
        ({GRPC_PATH_SW_STATUS: "disconnected", GRPC_PATH_SW_HISTORY: True}, False),
        ({}, False),
    ],
)
def test_subwoofer_currently_linked(
    snapshot: dict[str, object], expected: bool
) -> None:
    assert subwoofer_currently_linked(snapshot) is expected
