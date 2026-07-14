"""Decode GetCapabilities response and build GetStates path allowlists."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

_LOGGER = logging.getLogger(__name__)

_GET_CAPABILITIES_METHOD = (
    "/jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService/GetCapabilities"
)
_WIRE_TYPE_LEN = 2
_FIELD_CAPABILITIES = 1
_MAX_VARINT_SHIFT = 64


@dataclass(frozen=True, slots=True)
class CapabilityMeta:
    """Per-path metadata from GetCapabilities JSON."""

    name: str
    type: str
    min: int | None = None
    max: int | None = None


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


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def capability_index_from_json(
    cap_json: dict[str, Any] | str,
) -> dict[str, CapabilityMeta]:
    """Build path → CapabilityMeta from parsed GetCapabilities JSON."""
    if isinstance(cap_json, str):
        parsed: Any = json.loads(cap_json)
    else:
        parsed = cap_json
    if not isinstance(parsed, dict):
        return {}
    entries = parsed.get("capabilities")
    if not isinstance(entries, list):
        return {}
    index: dict[str, CapabilityMeta] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        props = entry.get("props") if isinstance(entry.get("props"), dict) else {}
        cap_type = entry.get("type")
        index[name] = CapabilityMeta(
            name=name,
            type=str(cap_type) if cap_type is not None else "unknown",
            min=_optional_int(props.get("min")),
            max=_optional_int(props.get("max")),
        )
    return index


def capability_path_names(cap_json: dict[str, Any] | str) -> frozenset[str]:
    """Return the set of capability ``name`` strings from parsed JSON."""
    return frozenset(capability_index_from_json(cap_json))


def parse_capability_index(raw: bytes) -> dict[str, CapabilityMeta] | None:
    """Decode GetCapabilities response bytes into a path metadata index."""
    text = decode_capabilities_json_text(raw)
    if not text:
        _LOGGER.debug("GetCapabilities response had no JSON text payload")
        return None
    try:
        index = capability_index_from_json(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        _LOGGER.debug("GetCapabilities JSON parse failed", exc_info=True)
        return None
    if not index:
        return None
    return index


def parse_capability_paths(raw: bytes) -> frozenset[str] | None:
    """Decode GetCapabilities response bytes into a path-name allowlist."""
    index = parse_capability_index(raw)
    if index is None:
        return None
    return frozenset(index)


def is_int_capability(
    path: str, capability_index: dict[str, CapabilityMeta] | None
) -> bool | None:
    """
    Return True/False when *path* is in the index; None when unknown.

    Callers should fall back to mapped int-path allowlists when this is None.
    """
    if capability_index is None:
        return None
    meta = capability_index.get(path)
    if meta is None:
        return None
    return meta.type == "int"


def int_range_from_capability(
    path: str, capability_index: dict[str, CapabilityMeta] | None
) -> tuple[int, int] | None:
    """Return (min, max) when both are present for an int capability path."""
    if capability_index is None:
        return None
    meta = capability_index.get(path)
    if meta is None or meta.type != "int":
        return None
    if meta.min is None or meta.max is None:
        return None
    return (meta.min, meta.max)


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
