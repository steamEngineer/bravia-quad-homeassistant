"""Tests for StartNotifyStates delta decoder."""

from custom_components.bravia_quad.grpc.get_states_request import encode_signed_varint
from custom_components.bravia_quad.grpc.notify_decode import (
    _maybe_signed_int,
    decode_notify_delta,
)

# Live capture: volume 50 after TCP bump (fw 001.454)
VOLUME_50_HEX = (
    "0a0e0a0c0a06766f6c756d6512020832"
    "122053117cf8b42ef7a89f371309801750bed9357a0981791d55446563d8262d277"
    "11a2461663538343932632d656164382d343862392d386631612d396536633566373331663032"
)


def test_decode_volume_delta() -> None:
    path, value = decode_notify_delta(VOLUME_50_HEX)
    assert path == "volume"
    assert value == 50


def test_decode_from_bytes() -> None:
    minimal = bytes.fromhex("0a0e0a0c0a06766f6c756d6512020832")
    path, value = decode_notify_delta(minimal)
    assert path == "volume"
    assert value == 50


def test_maybe_signed_int_negative() -> None:
    assert _maybe_signed_int(18446744073709551611) == -5
    assert _maybe_signed_int(5) == 5


def test_decode_negative_subwoofer_delta() -> None:
    """Negative levels arrive as unsigned int64 varints; decode as signed."""
    path_bytes = b"sound_setting.volume.subwoofer"
    nested = b"\x08" + encode_signed_varint(-5)
    path_field = b"\x0a" + bytes([len(path_bytes)]) + path_bytes
    value_field = b"\x12" + bytes([len(nested)]) + nested
    inner = path_field + value_field
    wrap_inner = b"\x0a" + bytes([len(inner)]) + inner
    outer = b"\x0a" + bytes([len(wrap_inner)]) + wrap_inner
    path, value = decode_notify_delta(outer)
    assert path == "sound_setting.volume.subwoofer"
    assert value == -5
