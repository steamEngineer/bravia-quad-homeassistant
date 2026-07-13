"""
Decode StartNotifyStates delta payloads (field path + value).

Notify updates arrive in ``StartNotifyStatesResponse.session_random`` — not
``states``. Wire format is a nested protobuf blob documented in grpc_test2 PoC.
"""

# ruff: noqa: PLR0911, PLR0912, PLR2004

from __future__ import annotations

from typing import Any


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        if not (byte & 0x80):
            break
        shift += 7
    return result, offset


def _decode_field(data: bytes, offset: int) -> tuple[tuple[int, int, Any] | None, int]:
    if offset >= len(data):
        return None, offset
    tag = data[offset]
    field_num = tag >> 3
    wire_type = tag & 0x7
    offset += 1
    if wire_type == 0:
        value, offset = _decode_varint(data, offset)
        return (field_num, wire_type, value), offset
    if wire_type == 2:
        length, offset = _decode_varint(data, offset)
        if offset + length > len(data):
            return None, offset
        value = data[offset : offset + length]
        offset += length
        return (field_num, wire_type, value), offset
    return None, offset


def _nested_varint(payload: bytes) -> int | None:
    field, _ = _decode_field(payload, 0)
    if field and field[0] == 1 and field[1] == 0:
        return int(field[2])
    return None


def _nested_string(payload: bytes) -> str | None:
    field, _ = _decode_field(payload, 0)
    if field and field[0] == 1 and field[1] == 2:
        try:
            return field[2].decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _maybe_signed_int(value: int) -> int:
    """Reinterpret protobuf int64 varints that arrived as unsigned."""
    if value >= 1 << 63:
        return value - (1 << 64)
    return value


def _extract_value(fields: dict[int, tuple[int, Any]]) -> Any:
    if 2 in fields:
        wire_type, raw = fields[2]
        if wire_type == 0:
            return _maybe_signed_int(int(raw)) if isinstance(raw, int) else raw
        if wire_type == 2 and raw:
            nested = _nested_varint(raw)
            if nested is not None:
                return _maybe_signed_int(nested)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text and all(c.isprintable() or c.isspace() for c in text):
                return text
            return raw.hex()
    if 3 in fields:
        wire_type, raw = fields[3]
        if wire_type == 2:
            if not raw:
                return False
            nested = _nested_varint(raw)
            if nested is not None:
                return bool(nested)
    for key in (4, 5):
        if key in fields:
            wire_type, raw = fields[key]
            if wire_type == 2 and raw:
                text = _nested_string(raw)
                if text is not None:
                    return text
    return None


def decode_notify_delta(payload: bytes | str) -> tuple[str | None, Any]:
    """Return ``(field_path, value)`` from a notify ``session_random`` blob."""
    if isinstance(payload, str):
        payload = bytes.fromhex(payload)
    offset = 0
    outer, offset = _decode_field(payload, offset)
    if not outer or outer[0] != 1 or outer[1] != 2:
        return None, None
    inner, _ = _decode_field(outer[2], 0)
    if not inner or inner[0] != 1 or inner[1] != 2:
        return None, None
    fields: dict[int, tuple[int, Any]] = {}
    pos = 0
    while pos < len(inner[2]):
        field, pos = _decode_field(inner[2], pos)
        if not field:
            break
        fields[field[0]] = (field[1], field[2])
    path = None
    if 1 in fields and fields[1][0] == 2:
        path = fields[1][1].decode("utf-8", errors="ignore")
    value = _extract_value(fields)
    if path and "sound_field" in path and isinstance(value, int) and value in (0, 1):
        value = bool(value)
    return path, value
