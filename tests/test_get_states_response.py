"""Tests for GetStatesWithAuth response parsing."""

from __future__ import annotations

from pathlib import Path

from custom_components.bravia_quad.grpc.get_states_request import encode_varint
from custom_components.bravia_quad.grpc.get_states_response import (
    parse_get_states_response,
)


def test_parse_empty_response() -> None:
    assert parse_get_states_response(b"") == {}


def test_parse_notify_shaped_delta() -> None:
    payload = bytes.fromhex("0a0e0a0c0a06766f6c756d6512020832")
    result = parse_get_states_response(payload)
    assert result == {"volume": 50}


def test_parse_varint_and_bool_entries() -> None:
    volume = bytes.fromhex("0a0c0a06766f6c756d6512020822")
    power = bytes.fromhex("0a0b0a05706f7765721a020801")
    rear = bytes.fromhex(
        "0a280a19736f756e645f73657474696e672e766f6c756d652e72656172"
        "120b08fdffffffffffffffff01"
    )
    sub = bytes.fromhex(
        "0a240a1e736f756e645f73657474696e672e766f6c756d652e737562776f6f66657212020801"
    )
    slm = bytes.fromhex(
        "0a370a31736f756e645f6f7074696d697a6174696f6e2e736c6d2e"
        "6d6561737572656d656e745f657374696d617465645f74696d6512020828"
    )
    stream = volume + power + rear + sub + slm
    payload = b"\x0a" + encode_varint(len(stream)) + stream
    result = parse_get_states_response(payload)
    assert result["volume"] == 34
    assert result["power"] is True
    assert result["sound_setting.volume.rear"] == -3
    assert result["sound_setting.volume.subwoofer"] == 1
    assert result["sound_optimization.slm.measurement_estimated_time"] == 40


def test_parse_sound_field_int_coercion() -> None:
    path = b"sound_setting.sound_field"
    path_field = b"\x0a" + encode_varint(len(path)) + path
    value_field = b"\x10\x00"
    inner = path_field + value_field
    entry = b"\x0a" + encode_varint(len(inner)) + inner
    payload = b"\x0a" + encode_varint(len(entry)) + entry
    result = parse_get_states_response(payload)
    assert result["sound_setting.sound_field"] is False


def test_parse_frida_full_snapshot() -> None:
    capture = (
        Path(__file__).resolve().parents[1] / ".cache/frida/getstates_rx_seq51.bin"
    )
    if not capture.is_file():
        return
    result = parse_get_states_response(capture.read_bytes())
    assert len(result) >= 170
    assert result["system_setting.friendly_name"] == "Office Quads"
    assert result["fw_update.version.main"] == "001.454"
    assert result["volume"] == 34
    assert result["power"] is True
    assert result["sound_setting.volume.rear"] == -3
    assert result["sound_setting.volume.subwoofer"] == 1
