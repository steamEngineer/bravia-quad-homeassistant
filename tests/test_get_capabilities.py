"""Tests for GetCapabilities decode and GetStates path filtering."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.bravia_quad.grpc.client import BraviaGrpcClient
from custom_components.bravia_quad.grpc.get_capabilities_response import (
    CapabilityMeta,
    capability_index_from_json,
    capability_path_names,
    decode_capabilities_json_text,
    filter_field_paths,
    int_range_from_capability,
    is_int_capability,
    parse_capability_index,
    parse_capability_paths,
)
from custom_components.bravia_quad.grpc.get_states_request import load_field_paths

FIXTURES = Path(__file__).parent / "fixtures"
CAP_JSON = FIXTURES / "get_capabilities_minimal.json"
CAP_BIN = FIXTURES / "get_capabilities_minimal.bin"


def test_capability_path_names_from_json() -> None:
    data = json.loads(CAP_JSON.read_text(encoding="utf-8"))
    names = capability_path_names(data)
    assert names == frozenset(
        {
            "power",
            "volume",
            "mute",
            "playback_control.function",
            "sound_setting.night_mode",
            "bluetooth_setting.connection_quality",
        }
    )


def test_parse_capability_paths_from_wire() -> None:
    raw = CAP_BIN.read_bytes()
    text = decode_capabilities_json_text(raw)
    assert text is not None
    names = parse_capability_paths(raw)
    assert names is not None
    assert "power" in names
    assert "volume" in names
    assert len(names) == 6


def test_filter_field_paths_preserves_order_and_drops_unknown() -> None:
    ha_paths = [
        "bluetooth_setting.connection_quality",
        "sound_setting.drc",
        "power",
        "not_on_device",
        "volume",
    ]
    allow = frozenset(
        {
            "bluetooth_setting.connection_quality",
            "power",
            "volume",
        }
    )
    filtered = filter_field_paths(ha_paths, allow)
    assert filtered == [
        "bluetooth_setting.connection_quality",
        "power",
        "volume",
    ]


def test_filter_field_paths_soft_fallback_when_none() -> None:
    ha_paths = ["power", "volume"]
    assert filter_field_paths(ha_paths, None) == ha_paths


def test_filter_field_paths_soft_fallback_when_empty_intersection() -> None:
    ha_paths = ["power", "volume"]
    assert filter_field_paths(ha_paths, frozenset({"other.path"})) == ha_paths


def test_field_paths_for_get_states_filters_and_falls_back() -> None:
    client = BraviaGrpcClient("127.0.0.1")
    ha_paths = load_field_paths()
    assert client.field_paths_for_get_states() == ha_paths

    client._capability_paths = frozenset(
        {
            "power",
            "volume",
            "mute",
            "bluetooth_setting.connection_quality",
        }
    )
    filtered = client.field_paths_for_get_states()
    assert filtered[0] == "bluetooth_setting.connection_quality"
    assert "power" in filtered
    assert "volume" in filtered
    assert "mute" in filtered
    assert "sound_setting.drc" not in filtered
    assert len(filtered) == 4

    client._capability_paths = frozenset({"totally.unknown.path"})
    assert client.field_paths_for_get_states() == ha_paths


def test_get_states_dict_uses_filtered_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BraviaGrpcClient("127.0.0.1")
    client.authenticated = True
    client.session_random = b"\x01" * 8
    client.session_id = "test-session"
    client.auth_token = b"\x02" * 32
    client._capability_paths = frozenset({"power", "volume"})

    captured: dict[str, object] = {}

    def fake_raw(request_bytes: bytes) -> tuple[bytes | None, str | None]:
        captured["request"] = request_bytes
        return b"\x00", None

    monkeypatch.setattr(client, "get_states_raw", fake_raw)
    monkeypatch.setattr(
        "custom_components.bravia_quad.grpc.client.parse_get_states_response",
        lambda _raw: {"power": True},
    )
    monkeypatch.setattr(client, "_apply_get_states_response_tokens", lambda _raw: None)

    built_paths: list[str] = []

    def fake_build(
        field_paths: list[str],
        *,
        session_random: bytes,
        session_id: str,
        auth_token: bytes,
    ) -> bytes:
        built_paths.extend(field_paths)
        return b"req"

    monkeypatch.setattr(
        "custom_components.bravia_quad.grpc.client.build_get_states_with_auth_request",
        fake_build,
    )

    result = client.get_states_dict()
    assert result == {"power": True}
    assert built_paths == ["power", "volume"]
    assert captured["request"] == b"req"


def test_capability_index_includes_type_and_range() -> None:
    data = {
        "capabilities": [
            {
                "name": "sound_setting.volume.rear",
                "type": "int",
                "props": {
                    "get": True,
                    "notify": True,
                    "commands": ["set"],
                    "min": -10,
                    "max": 10,
                    "span": 1,
                },
            },
            {
                "name": "power",
                "type": "bool",
                "props": {"get": True, "notify": True, "commands": ["set"]},
            },
            {
                "name": "volume",
                "type": "int",
                "props": {"get": True, "notify": True, "commands": ["set"]},
            },
        ]
    }
    index = capability_index_from_json(data)
    assert index["sound_setting.volume.rear"] == CapabilityMeta(
        name="sound_setting.volume.rear",
        type="int",
        min=-10,
        max=10,
    )
    assert is_int_capability("sound_setting.volume.rear", index) is True
    assert is_int_capability("power", index) is False
    assert is_int_capability("missing", index) is None
    assert int_range_from_capability("sound_setting.volume.rear", index) == (-10, 10)
    assert int_range_from_capability("volume", index) is None


def test_parse_capability_index_from_wire() -> None:
    raw = CAP_BIN.read_bytes()
    index = parse_capability_index(raw)
    assert index is not None
    assert index["volume"].type == "int"
    assert index["power"].type == "bool"
    assert parse_capability_paths(raw) == frozenset(index)


def test_fetch_capabilities_caches_index(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BraviaGrpcClient("127.0.0.1")
    client.channel = MagicMock()
    unary = MagicMock()
    unary.future.return_value.result.return_value = CAP_BIN.read_bytes()
    monkeypatch.setattr(client, "_get_capabilities_unary_callable", lambda: unary)

    names = client.fetch_capabilities()
    assert names is not None
    assert client.capability_paths == names
    assert client.capability_index is not None
    assert client.is_int_capability("volume") is True
    assert client.is_int_capability("power") is False
    assert "power" in names
    assert len(client.field_paths_for_get_states()) >= 3


def test_fetch_capabilities_soft_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BraviaGrpcClient("127.0.0.1")
    client.channel = MagicMock()
    unary = MagicMock()
    unary.future.return_value.result.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client, "_get_capabilities_unary_callable", lambda: unary)

    assert client.fetch_capabilities() is None
    assert client.capability_paths is None
    assert client.capability_index is None
    assert client.field_paths_for_get_states() == load_field_paths()
