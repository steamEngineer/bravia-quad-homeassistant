"""Parse GetStatesWithAuth response bytes into field-path values."""

from __future__ import annotations

from typing import Any

from .notify_decode import (
    _decode_field,
    _decode_varint,
    _nested_string,
    _nested_varint,
)


def parse_get_states_response(raw: bytes) -> dict[str, Any]:
    """
    Decode GetStatesWithAuth response into ``{field_path: value}``.

    Wire layout (fw 001.454): top-level field 2 holds field 1, a concatenated
    stream of ``path + value`` entries (not notify-shaped deltas).
    """
    result: dict[str, Any] = {}
    offset = 0
    while offset < len(raw):
        field, offset = _decode_field(raw, offset)
        if not field:
            break
        field_num, wire_type, payload = field
        if wire_type != 2 or not isinstance(payload, bytes):
            continue
        if field_num == 1:
            _parse_entries_stream(payload, result)
        else:
            _parse_states_blob(payload, result)
    return result


def _parse_states_blob(blob: bytes, out: dict[str, Any]) -> None:
    """Walk nested length-delimited fields for entry streams."""
    pos = 0
    while pos < len(blob):
        field, pos = _decode_field(blob, pos)
        if not field:
            break
        field_num, wire_type, payload = field
        if wire_type != 2 or not isinstance(payload, bytes):
            continue
        if field_num == 1:
            _parse_entries_stream(payload, out)
        else:
            path, value = _parse_state_entry(payload)
            if path:
                out[path] = value


def _parse_entries_stream(stream: bytes, out: dict[str, Any]) -> None:
    pos = 0
    while pos < len(stream):
        if stream[pos] != 0x0A:
            break
        path, value, consumed = _parse_one_entry(stream[pos:])
        if consumed <= 0:
            break
        pos += consumed
        if path:
            out[path] = value


def _parse_one_entry(data: bytes) -> tuple[str | None, Any, int]:
    if not data or data[0] != 0x0A:
        return None, None, 0
    entry_len, i = _decode_varint(data, 1)
    if i + entry_len > len(data):
        return None, None, 0
    chunk = data[i : i + entry_len]
    path, value = _parse_state_entry(chunk)
    return path, value, i + entry_len


def _parse_state_entry(payload: bytes) -> tuple[str | None, Any]:
    path: str | None = None
    fields: dict[int, tuple[int, Any]] = {}
    pos = 0
    while pos < len(payload):
        field, pos = _decode_field(payload, pos)
        if not field:
            break
        field_num, wire_type, field_payload = field
        if field_num == 1 and wire_type == 2 and isinstance(field_payload, bytes):
            try:
                path = field_payload.decode("utf-8")
            except UnicodeDecodeError:
                path = None
        else:
            fields[field_num] = (wire_type, field_payload)
    value = _extract_get_states_value(fields)
    if path and "sound_field" in path and isinstance(value, int) and value in (0, 1):
        value = bool(value)
    return path, value


def _extract_get_states_value(fields: dict[int, tuple[int, Any]]) -> Any:
    """Extract value from GetStates entry fields (2=int, 3=bool, 4=str, 5=bytes/json)."""
    if 4 in fields:
        wire_type, raw = fields[4]
        if wire_type == 2 and isinstance(raw, bytes):
            text = _nested_string(raw)
            if text is not None:
                return text
    if 2 in fields:
        wire_type, raw = fields[2]
        if wire_type == 0:
            return _maybe_signed_int(raw)
        if wire_type == 2 and isinstance(raw, bytes):
            nested = _nested_varint(raw)
            if nested is not None:
                return _maybe_signed_int(nested)
            text = _nested_string(raw)
            if text is not None:
                return text
    if 3 in fields:
        wire_type, raw = fields[3]
        if wire_type == 2 and isinstance(raw, bytes):
            if not raw:
                return None
            nested = _nested_varint(raw)
            if nested is not None:
                return bool(nested)
    if 5 in fields:
        wire_type, raw = fields[5]
        if wire_type == 2 and isinstance(raw, bytes):
            if not raw:
                return None
            text = _nested_string(raw)
            if text is not None:
                return text
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.hex()
            if text and all(c.isprintable() or c in "\n\r\t" for c in text):
                return text
            return raw.hex()
    return None


def _maybe_signed_int(value: int) -> int:
    if value >= 1 << 63:
        return value - (1 << 64)
    return value
