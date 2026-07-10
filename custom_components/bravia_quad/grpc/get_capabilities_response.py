"""Decode GetCapabilities response and build GetStates path allowlists."""

from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

_GET_CAPABILITIES_METHOD = (
    "/jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService/GetCapabilities"
)
_WIRE_TYPE_LEN = 2
_FIELD_CAPABILITIES = 1
_MAX_VARINT_SHIFT = 64


def get_capabilities_method() -> str:
    """Return the fully-qualified GetCapabilities RPC path."""
    return _GET_CAPABILITIES_METHOD


def _read_varint(data: bytes, index: int) -> tuple[int, int]:
    """Decode a protobuf varint; return (value, next_index)."""
    value = 0
    shift = 0
    while index < len(data):
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, index
        shift += 7
        if shift >= _MAX_VARINT_SHIFT:
            break
    msg = "truncated protobuf varint"
    raise ValueError(msg)


def decode_capabilities_json_text(raw: bytes) -> str | None:
    """
    Extract JSON text from a GetCapabilities response.

    Wire layout observed on HT-A9M2: outer field 1 (length-delimited) wrapping
    an inner field 1 string payload with ``{"capabilities":[...]}``.
    """
    index = 0
    while index < len(raw):
        tag = raw[index]
        index += 1
        field = tag >> 3
        wire = tag & 0x07
        if wire != _WIRE_TYPE_LEN or field != _FIELD_CAPABILITIES:
            break
        length, index = _read_varint(raw, index)
        end = index + length
        if end > len(raw):
            break
        cap_blob = raw[index:end]
        index = end
        inner = 0
        while inner < len(cap_blob):
            ctag = cap_blob[inner]
            inner += 1
            cfield = ctag >> 3
            cwire = ctag & 0x07
            if cwire != _WIRE_TYPE_LEN:
                break
            payload_len, inner = _read_varint(cap_blob, inner)
            payload = cap_blob[inner : inner + payload_len]
            inner += payload_len
            if cfield == _FIELD_CAPABILITIES:
                return payload.decode("utf-8")
    return None


def capability_path_names(cap_json: dict[str, Any] | str) -> frozenset[str]:
    """Return the set of capability ``name`` strings from parsed JSON."""
    if isinstance(cap_json, str):
        parsed: Any = json.loads(cap_json)
    else:
        parsed = cap_json
    if not isinstance(parsed, dict):
        return frozenset()
    entries = parsed.get("capabilities")
    if not isinstance(entries, list):
        return frozenset()
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return frozenset(names)


def parse_capability_paths(raw: bytes) -> frozenset[str] | None:
    """Decode GetCapabilities response bytes into a path-name allowlist."""
    text = decode_capabilities_json_text(raw)
    if not text:
        _LOGGER.debug("GetCapabilities response had no JSON text payload")
        return None
    try:
        names = capability_path_names(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        _LOGGER.debug("GetCapabilities JSON parse failed", exc_info=True)
        return None
    if not names:
        return None
    return names


def filter_field_paths(
    ha_paths: list[str], capability_paths: frozenset[str] | None
) -> list[str]:
    """
    Intersect HA path list with device capabilities, preserving HA order.

    When *capability_paths* is None or the intersection is empty, return
    *ha_paths* unchanged (soft fallback).
    """
    if capability_paths is None:
        return list(ha_paths)
    filtered = [path for path in ha_paths if path in capability_paths]
    if not filtered:
        return list(ha_paths)
    return filtered
