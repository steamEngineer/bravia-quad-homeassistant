"""Build device capability scrape reports (pure analysis, no I/O)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bravia_quad.grpc.get_capabilities_response import decode_capabilities_json_text
from bravia_quad.grpc.get_states_request import load_field_paths
from bravia_quad.grpc_mapping import (
    GRPC_TCP_MAPPINGS,
    NOTIFY_ONLY_GRPC_PATHS_SET,
    entity_critical_grpc_paths,
)
from bravia_quad.transport import identity_from_grpc_snapshot

REPORT_SCHEMA_VERSION = 1

_METADATA_SUFFIXES = (".availability", ".unavailable_reason", ".range")
# Keep in sync with bravia_quad.grpc_seeds_seed.SEEDS_SEED_PATHS (avoid HA import here).
_SEEDS_SEED_PATHS = NOTIFY_ONLY_GRPC_PATHS_SET | frozenset(
    {"sound_setting.sound_effect"}
)
_SEEDS_PROBE_PATHS = _SEEDS_SEED_PATHS

_SPEAKER_STATUS_PATHS = (
    "speaker_connection_setting.connection_status.fl",
    "speaker_connection_setting.connection_status.fr",
    "speaker_connection_setting.connection_status.rl",
    "speaker_connection_setting.connection_status.rr",
    "speaker_connection_setting.connection_status.sw",
)

_PII_KEYS = frozenset(
    {
        "device_id",
        "access_token",
        "refresh_token",
        "session_key",
        "hmac_key",
        "key_id",
        "serial",
        "serial_number",
        "mac",
        "ipv4_address",
        "ipv6_address",
        "wifi_mac_address_wired",
        "wifi_mac_address_wireless",
        "friendly_name",
        "time_zone",
        "timezone",
    }
)

_REDACTED = "[redacted]"

# gRPC dot-paths (or path fragments) treated as PII in shareable reports.
_PII_PATH_FRAGMENTS = (
    "serial",
    "friendly_name",
    "ipv4",
    "ipv6",
    "time_zone",
    "btaddr",
    "wifi_mac",
    "mac_address",
    "device_id",
    # Now-playing / playlist metadata (listening history).
    "playback_control.title",
    "playback_control.artist",
    "playback_control.album",
    "playback_control.jacket_url",
    "playback_control.spotify_playlist_name",
    "playback_control.bt_device_name",
    # Room layout / speaker placement coordinates.
    "sound_gps.speaker_location",
)


def _is_pii_grpc_path(path: str) -> bool:
    """Return True when a gRPC field path carries shareable-report PII."""
    return any(frag in path for frag in _PII_PATH_FRAGMENTS)


@dataclass(frozen=True, slots=True)
class CapabilityEntry:
    """Parsed GetCapabilities row."""

    name: str
    cap_type: str
    cap_get: bool
    cap_set: bool
    cap_notify: bool
    enum_values: tuple[str, ...]
    props: dict[str, Any]


def decode_get_capabilities_response(raw: bytes) -> dict[str, Any]:
    """Parse GetCapabilitiesResponse wire bytes via integration decoder."""
    out: dict[str, Any] = {"raw_len": len(raw)}
    text = decode_capabilities_json_text(raw)
    if text is not None:
        out["format"] = "text"
        out["text"] = text
    return out


def integration_version(repo_root: Path | None = None) -> str:
    """Read integration version from manifest.json."""
    root = repo_root or Path(__file__).resolve().parents[2]
    manifest = root / "custom_components" / "bravia_quad" / "manifest.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    version = payload.get("version")
    return str(version) if version else "unknown"


def value_type_of(value: Any) -> str:
    """Classify an observed live value for quirk ingest."""
    type_map: dict[type, str] = {
        bool: "bool",
        int: "int",
        float: "float",
        str: "str",
        list: "list",
        dict: "dict",
    }
    if value is None:
        return "null"
    # bool is a subclass of int — check explicitly first.
    if isinstance(value, bool):
        return "bool"
    for py_type, label in type_map.items():
        if py_type is bool:
            continue
        if isinstance(value, py_type):
            return label
    return "other"


def build_local_vs_seeds(
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
) -> dict[str, Any]:
    """Compare paths present in both local GetStates and Seeds cloud."""
    both = sorted(
        path
        for path in set(grpc_snapshot) & set(seeds_flat)
        if grpc_snapshot.get(path) is not None and seeds_flat.get(path) is not None
    )
    equal: list[str] = []
    unequal: list[dict[str, Any]] = []
    for path in both:
        local = grpc_snapshot[path]
        cloud = seeds_flat[path]
        if local == cloud:
            equal.append(path)
        else:
            unequal.append(
                {
                    "path": path,
                    "local_value": local,
                    "seeds_value": cloud,
                    "local_value_type": value_type_of(local),
                    "seeds_value_type": value_type_of(cloud),
                }
            )
    return {
        "both_present_count": len(both),
        "equal_count": len(equal),
        "unequal_count": len(unequal),
        "equal_paths": equal,
        "unequal": unequal,
    }


def build_capability_index(
    capabilities_json: dict[str, Any] | None,
) -> dict[str, CapabilityEntry]:
    """Index capability entries by path name."""
    if not capabilities_json:
        return {}
    rows = capabilities_json.get("capabilities")
    if not isinstance(rows, list):
        return {}
    index: dict[str, CapabilityEntry] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str):
            continue
        props = row.get("props") if isinstance(row.get("props"), dict) else {}
        commands = (
            props.get("commands") if isinstance(props.get("commands"), list) else []
        )
        values = props.get("values") if isinstance(props.get("values"), list) else []
        index[name] = CapabilityEntry(
            name=name,
            cap_type=str(row.get("type", "unknown")),
            cap_get=bool(props.get("get")),
            cap_set="set" in commands,
            cap_notify=bool(props.get("notify")),
            enum_values=tuple(str(v) for v in values),
            props=props,
        )
    return index


def _is_leaf(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def flatten_seeds_states(payload: Any, prefix: str = "") -> dict[str, Any]:
    """Walk Seeds JSON and collect dot-path keys."""
    flat: dict[str, Any] = {}
    if isinstance(payload, dict):
        if "name" in payload and "value" in payload and _is_leaf(payload["value"]):
            flat[str(payload["name"])] = payload["value"]
            return flat
        if "path" in payload and "value" in payload and _is_leaf(payload["value"]):
            flat[str(payload["path"])] = payload["value"]
            return flat
        for key, value in payload.items():
            if key in ("device_id", "updated_at", "timestamp", "hmac"):
                continue
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if _is_leaf(value):
                flat[child_prefix] = value
            else:
                flat.update(flatten_seeds_states(value, child_prefix))
        return flat
    if isinstance(payload, list):
        for item in payload:
            flat.update(flatten_seeds_states(item, prefix))
        return flat
    if prefix:
        flat[prefix] = payload
    return flat


def _capability_path_names(index: dict[str, CapabilityEntry]) -> set[str]:
    return set(index.keys())


def _is_metadata_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _METADATA_SUFFIXES)


def _device_gates_for_path(path: str, hardware: dict[str, Any]) -> list[str]:
    gates: list[str] = []
    if path == "sound_setting.volume.subwoofer" and not hardware.get("has_subwoofer"):
        gates.append("requires_subwoofer")
    if path == "sound_setting.volume.rear" and not hardware.get("has_rear_speakers"):
        gates.append("requires_rear_speakers")
    return gates


def build_hardware_profile(
    grpc_snapshot: dict[str, Any],
    cap_index: dict[str, CapabilityEntry],
) -> dict[str, Any]:
    """Derive hardware gates and topology from live snapshot."""
    identity = identity_from_grpc_snapshot(grpc_snapshot)
    has_subwoofer = bool(identity.get("has_subwoofer"))
    bass_unavail = grpc_snapshot.get("sound_setting.volume.bass.unavailable_reason")
    if bass_unavail == "no_speaker":
        has_subwoofer = False

    sw_status = grpc_snapshot.get("speaker_connection_setting.connection_status.sw")
    rear_rl = grpc_snapshot.get("speaker_connection_setting.connection_status.rl")
    rear_rr = grpc_snapshot.get("speaker_connection_setting.connection_status.rr")
    has_rear = any(
        status in ("connected", "protected") for status in (rear_rl, rear_rr)
    )

    speaker_topology: dict[str, Any] = {}
    for path in _SPEAKER_STATUS_PATHS:
        short = path.rsplit(".", maxsplit=1)[-1]
        speaker_topology[short] = grpc_snapshot.get(path)

    playback_inputs = grpc_snapshot.get("playback_control.function.available_values")
    if playback_inputs is None and "playback_control.function" in cap_index:
        playback_inputs = cap_index["playback_control.function"].enum_values

    return {
        "model_id": identity.get("model_id")
        or grpc_snapshot.get("system_setting.model_name"),
        "model_name": identity.get("model"),
        "manufacturer": identity.get("manufacturer"),
        "friendly_name": identity.get("name"),
        "serial": identity.get("serial_number"),
        "mac": identity.get("mac"),
        "firmware": grpc_snapshot.get("fw_update.version.main"),
        "has_subwoofer": has_subwoofer,
        "has_rear_speakers": has_rear,
        "subwoofer_connected": sw_status in ("connected", "protected"),
        "speaker_topology": speaker_topology,
        "playback_inputs_available": playback_inputs,
        "bass_unavailable_reason": bass_unavail,
    }


def _matrix_row(
    *,
    path: str,
    ha_platform: str | None,
    tcp_feature: str | None,
    mapping_verified: bool | None,
    cap_entry: CapabilityEntry | None,
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
    hardware: dict[str, Any],
    mapping_exists: bool,
) -> dict[str, Any]:
    avail_path = f"{path}.availability"
    availability = grpc_snapshot.get(avail_path)
    if availability is None:
        availability = _live_value(avail_path, grpc_snapshot, seeds_flat)
    read_source = _read_source(path, grpc_snapshot, seeds_flat, cap_entry)
    live = _live_value(path, grpc_snapshot, seeds_flat)
    return {
        "grpc_path": path,
        "ha_platform": ha_platform,
        "tcp_feature": tcp_feature,
        "mapping_verified": mapping_verified,
        "cap_get": cap_entry.cap_get if cap_entry else None,
        "cap_set": cap_entry.cap_set if cap_entry else None,
        "cap_notify": cap_entry.cap_notify if cap_entry else None,
        "cap_type": cap_entry.cap_type if cap_entry else None,
        "enum_values": list(cap_entry.enum_values) if cap_entry else [],
        "live_value": live,
        "value_type": value_type_of(live),
        "read_source": read_source,
        "availability": availability,
        "suggested_enabled_default": _suggested_enabled_default(
            path,
            cap_entry,
            availability,
            hardware,
            mapping_verified,
        ),
        "device_gates": _device_gates_for_path(path, hardware),
        "ha_status": _ha_status(
            path,
            mapping_exists,
            read_source,
            cap_entry,
            grpc_snapshot,
            seeds_flat,
        ),
    }


def _live_value(
    path: str,
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
) -> Any:
    if path in grpc_snapshot and grpc_snapshot[path] is not None:
        return grpc_snapshot[path]
    return seeds_flat.get(path)


def _read_source(
    path: str,
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
    cap_entry: CapabilityEntry | None,
) -> str:
    if path in grpc_snapshot and grpc_snapshot[path] is not None:
        return "local_grpc"
    if path in seeds_flat:
        return "seeds_cloud"
    if cap_entry is None:
        return "n/a"
    if not cap_entry.cap_get and cap_entry.cap_set:
        return "unreadable"
    if cap_entry.cap_get:
        return "unreadable"
    return "n/a"


def _suggested_enabled_default(
    path: str,
    cap_entry: CapabilityEntry | None,
    availability: Any,
    hardware: dict[str, Any],
    mapping_verified: bool | None,
) -> bool:
    gates = _device_gates_for_path(path, hardware)
    if gates:
        return False
    if cap_entry is None:
        return bool(mapping_verified)
    if not cap_entry.cap_get:
        return False
    return availability is not False


def _ha_status(
    path: str,
    mapping_exists: bool,
    read_source: str,
    cap_entry: CapabilityEntry | None,
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
) -> str:
    if not mapping_exists:
        if cap_entry and not _is_metadata_path(path):
            return "unmapped_new"
        return "n/a"
    if read_source == "unreadable":
        if path in NOTIFY_ONLY_GRPC_PATHS_SET and cap_entry and cap_entry.cap_set:
            return "notify_only_regression"
        return "mapped_missing_live"
    if (
        path in NOTIFY_ONLY_GRPC_PATHS_SET
        and path not in grpc_snapshot
        and path not in seeds_flat
        and cap_entry
        and cap_entry.cap_set
    ):
        return "notify_only_regression"
    return "mapped"


def build_entity_matrix(
    *,
    cap_index: dict[str, CapabilityEntry],
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
    hardware: dict[str, Any],
) -> list[dict[str, Any]]:
    """One row per HA mapping plus notable unmapped capability paths."""
    rows: list[dict[str, Any]] = []
    mapped_paths = {m.grpc_path for m in GRPC_TCP_MAPPINGS}

    for mapping in GRPC_TCP_MAPPINGS:
        path = mapping.grpc_path
        rows.append(
            _matrix_row(
                path=path,
                ha_platform=mapping.ha_platform,
                tcp_feature=mapping.tcp_feature,
                mapping_verified=mapping.verified,
                cap_entry=cap_index.get(path),
                grpc_snapshot=grpc_snapshot,
                seeds_flat=seeds_flat,
                hardware=hardware,
                mapping_exists=True,
            )
        )

    ha_entity_paths = entity_critical_grpc_paths()
    for path in sorted(_capability_path_names(cap_index) - mapped_paths):
        if _is_metadata_path(path):
            continue
        if path in ha_entity_paths:
            continue
        cap_entry = cap_index[path]
        if cap_entry.cap_type == "void":
            continue
        rows.append(
            _matrix_row(
                path=path,
                ha_platform=None,
                tcp_feature=None,
                mapping_verified=None,
                cap_entry=cap_entry,
                grpc_snapshot=grpc_snapshot,
                seeds_flat=seeds_flat,
                hardware=hardware,
                mapping_exists=False,
            )
        )
    return rows


def build_diff_sections(
    *,
    cap_index: dict[str, CapabilityEntry],
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
    entity_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize capability vs HA mapping gaps."""
    ha_field_paths = set(load_field_paths())
    cap_paths = _capability_path_names(cap_index)
    mapped_paths = {m.grpc_path for m in GRPC_TCP_MAPPINGS}

    capability_only = sorted(
        p
        for p in cap_paths - ha_field_paths
        if not _is_metadata_path(p) and p not in mapped_paths
    )
    ha_not_in_capabilities = sorted(ha_field_paths - cap_paths)
    notify_only_regressions = sorted(
        row["grpc_path"]
        for row in entity_matrix
        if row.get("ha_status") == "notify_only_regression"
    )
    mapped_missing_live = sorted(
        row["grpc_path"]
        for row in entity_matrix
        if row.get("ha_status") == "mapped_missing_live"
        and row.get("grpc_path") in mapped_paths
    )
    unmapped_new = sorted(
        row["grpc_path"]
        for row in entity_matrix
        if row.get("ha_status") == "unmapped_new"
    )[:80]

    seeds_coverage = [
        {
            "path": path,
            "present": path in seeds_flat,
            "value": seeds_flat.get(path),
            "in_notify_only": path in NOTIFY_ONLY_GRPC_PATHS_SET,
            "in_seeds_seed_paths": path in _SEEDS_SEED_PATHS,
        }
        for path in sorted(_SEEDS_PROBE_PATHS)
    ]

    entity_ok = sum(
        1
        for path in entity_critical_grpc_paths()
        if grpc_snapshot.get(path) is not None or seeds_flat.get(path) is not None
    )

    return {
        "capability_path_count": len(cap_paths),
        "ha_field_path_count": len(ha_field_paths),
        "mapped_entity_count": len(mapped_paths),
        "entity_paths_with_live_value": entity_ok,
        "entity_paths_total": len(entity_critical_grpc_paths()),
        "capability_only_paths": capability_only[:80],
        "ha_paths_missing_from_capabilities": ha_not_in_capabilities,
        "notify_only_regressions": notify_only_regressions,
        "mapped_missing_live": mapped_missing_live,
        "unmapped_new_candidates": unmapped_new,
        "seeds_coverage": seeds_coverage,
        "local_vs_seeds": build_local_vs_seeds(grpc_snapshot, seeds_flat),
    }


def _slug_part(value: Any, fallback: str = "unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", text)[:48]


def report_filename_stem(
    hardware: dict[str, Any], *, timestamp: str | None = None
) -> str:
    """Build ``device-scrape-{model}-{fw}-{ts}`` stem."""
    ts = timestamp or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    model = _slug_part(hardware.get("model_id"))
    fw = _slug_part(hardware.get("firmware"), "fw")
    return f"device-scrape-{model}-{fw}-{ts}"


def _merge_http_identity(
    hardware: dict[str, Any], http_identity: dict[str, Any] | None
) -> dict[str, Any]:
    """Fill model/firmware from HTTP when gRPC snapshot omits them."""
    if not http_identity:
        return hardware
    merged = dict(hardware)
    if not merged.get("model_id") and http_identity.get("model_id"):
        merged["model_id"] = http_identity["model_id"]
        if not merged.get("model_name"):
            merged["model_name"] = http_identity["model_id"]
    if not merged.get("firmware") and http_identity.get("firmware"):
        merged["firmware"] = http_identity["firmware"]
    return merged


def build_full_report(
    *,
    host: str,
    auth_gate: dict[str, Any],
    capabilities_raw: dict[str, Any],
    capabilities_json: dict[str, Any] | None,
    grpc_snapshot: dict[str, Any],
    seeds_flat: dict[str, Any],
    seeds_latency_ms: float | None,
    scrape_meta: dict[str, Any],
    tcp_parity: dict[str, Any] | None = None,
    tcp_reachable: dict[str, Any] | None = None,
    http_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the complete scrape report dict."""
    cap_index = build_capability_index(capabilities_json)
    hardware = _merge_http_identity(
        build_hardware_profile(grpc_snapshot, cap_index), http_identity
    )
    entity_matrix = build_entity_matrix(
        cap_index=cap_index,
        grpc_snapshot=grpc_snapshot,
        seeds_flat=seeds_flat,
        hardware=hardware,
    )
    diffs = build_diff_sections(
        cap_index=cap_index,
        grpc_snapshot=grpc_snapshot,
        seeds_flat=seeds_flat,
        entity_matrix=entity_matrix,
    )
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "integration_version": integration_version(),
        "generated_at": datetime.now(UTC).isoformat(),
        "host": host,
        "auth_gate": auth_gate,
        "hardware_profile": hardware,
        "scrape_meta": scrape_meta,
        "capabilities": {
            "ok": capabilities_raw.get("ok"),
            "latency_s": capabilities_raw.get("latency_s"),
            "path_count": len(cap_index),
            "json": capabilities_json,
        },
        "grpc_snapshot_field_count": len(grpc_snapshot),
        "grpc_snapshot": grpc_snapshot,
        "seeds": {
            "path_count": len(seeds_flat),
            "latency_ms": seeds_latency_ms,
            "flat": seeds_flat,
        },
        "http_identity": http_identity,
        "tcp_reachable": tcp_reachable,
        "tcp_parity": tcp_parity,
        "diffs": diffs,
        "entity_matrix": entity_matrix,
    }


def _redact_value(key: str, value: Any) -> Any:
    if key in _PII_KEYS:
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _redact_snapshot_dict(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        path: (_REDACTED if _is_pii_grpc_path(path) else value)
        for path, value in snapshot.items()
    }


def _redact_entity_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        path = str(item.get("grpc_path", ""))
        if _is_pii_grpc_path(path) and item.get("live_value") is not None:
            item["live_value"] = _REDACTED
        redacted.append(item)
    return redacted


def _redact_seeds_coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        path = str(item.get("path", ""))
        if _is_pii_grpc_path(path) and "value" in item:
            item["value"] = _REDACTED
        redacted.append(item)
    return redacted


def _redact_local_vs_seeds(section: dict[str, Any]) -> dict[str, Any]:
    out = dict(section)
    unequal = []
    for row in section.get("unequal") or []:
        item = dict(row)
        path = str(item.get("path", ""))
        if _is_pii_grpc_path(path):
            if "local_value" in item:
                item["local_value"] = _REDACTED
            if "seeds_value" in item:
                item["seeds_value"] = _REDACTED
        unequal.append(item)
    out["unequal"] = unequal
    return out


def redact_report(
    report: dict[str, Any], *, include_pii: bool = False
) -> dict[str, Any]:
    """Return a copy with PII redacted unless *include_pii*."""
    if include_pii:
        return report
    redacted = dict(report)
    redacted["host"] = _REDACTED
    if "hardware_profile" in redacted:
        hp = dict(redacted["hardware_profile"])
        for key in ("serial", "mac", "friendly_name"):
            if key in hp:
                hp[key] = _REDACTED
        redacted["hardware_profile"] = hp
    if "grpc_snapshot" in redacted:
        redacted["grpc_snapshot"] = _redact_snapshot_dict(redacted["grpc_snapshot"])
    if "seeds" in redacted and isinstance(redacted["seeds"], dict):
        seeds = dict(redacted["seeds"])
        if "flat" in seeds and isinstance(seeds["flat"], dict):
            seeds["flat"] = _redact_snapshot_dict(seeds["flat"])
        redacted["seeds"] = seeds
    if "entity_matrix" in redacted:
        redacted["entity_matrix"] = _redact_entity_matrix(redacted["entity_matrix"])
    if "diffs" in redacted and isinstance(redacted["diffs"], dict):
        diffs = dict(redacted["diffs"])
        if "seeds_coverage" in diffs:
            diffs["seeds_coverage"] = _redact_seeds_coverage(diffs["seeds_coverage"])
        if "local_vs_seeds" in diffs and isinstance(diffs["local_vs_seeds"], dict):
            diffs["local_vs_seeds"] = _redact_local_vs_seeds(diffs["local_vs_seeds"])
        redacted["diffs"] = diffs
    if "auth_gate" in redacted:
        ag = dict(redacted["auth_gate"])
        for key in ("device_id", "access_token", "session_key", "hmac_key"):
            if key in ag:
                ag[key] = _REDACTED
        redacted["auth_gate"] = ag
    return redacted


def render_markdown(report: dict[str, Any]) -> str:
    """GitHub-issue-ready summary."""
    hw = report.get("hardware_profile") or {}
    diffs = report.get("diffs") or {}
    tcp = report.get("tcp_reachable") or {}
    local_vs = diffs.get("local_vs_seeds") or {}
    lines = [
        "# Device capability scrape",
        "",
        f"- **Generated:** {report.get('generated_at', 'unknown')}",
        f"- **Report schema:** {report.get('report_schema_version', 'unknown')}",
        f"- **Integration version:** {report.get('integration_version', 'unknown')}",
        f"- **Model:** {hw.get('model_id', 'unknown')} ({hw.get('model_name', '')})",
        f"- **Firmware:** {hw.get('firmware', 'unknown')}",
        f"- **Has subwoofer:** {hw.get('has_subwoofer')}",
        f"- **Has rear speakers:** {hw.get('has_rear_speakers')}",
        f"- **TCP :33336 reachable:** {tcp.get('reachable', 'unknown')}",
        "",
        "## Coverage",
        "",
        f"- Capability paths: {diffs.get('capability_path_count', 0)}",
        f"- Entity paths with live value: "
        f"{diffs.get('entity_paths_with_live_value', 0)}/"
        f"{diffs.get('entity_paths_total', 0)}",
        f"- gRPC snapshot fields: {report.get('grpc_snapshot_field_count', 0)}",
        f"- Seeds paths: {(report.get('seeds') or {}).get('path_count', 0)}",
        f"- Local∩Seeds equal/unequal: "
        f"{local_vs.get('equal_count', 0)}/"
        f"{local_vs.get('unequal_count', 0)}",
        "",
        "## Speaker topology",
        "",
    ]
    topo = hw.get("speaker_topology") or {}
    if topo:
        for key, value in sorted(topo.items()):
            lines.append(f"- **{key}:** {value}")
    else:
        lines.append("- (no speaker status paths in snapshot)")

    lines.extend(["", "## Notify-only regressions", ""])
    regressions = diffs.get("notify_only_regressions") or []
    if regressions:
        lines.extend(f"- `{path}`" for path in regressions)
    else:
        lines.append("- None detected")

    lines.extend(["", "## Mapped entities missing live read", ""])
    missing = diffs.get("mapped_missing_live") or []
    if missing:
        lines.extend(f"- `{path}`" for path in missing[:30])
        if len(missing) > 30:
            lines.append(f"- … and {len(missing) - 30} more")
    else:
        lines.append("- None")

    lines.extend(["", "## New capability paths (unmapped)", ""])
    unmapped = diffs.get("unmapped_new_candidates") or []
    if unmapped:
        lines.extend(f"- `{path}`" for path in unmapped[:25])
        if len(unmapped) > 25:
            lines.append(f"- … and {len(unmapped) - 25} more")
    else:
        lines.append("- None")

    unequal = local_vs.get("unequal") or []
    lines.extend(["", "## Local vs Seeds mismatches", ""])
    if unequal:
        lines.extend(
            f"- `{row['path']}`: local={row.get('local_value')!r} "
            f"seeds={row.get('seeds_value')!r}"
            for row in unequal[:20]
        )
        if len(unequal) > 20:
            lines.append(f"- … and {len(unequal) - 20} more")
    else:
        lines.append("- None")

    lines.extend(["", "## Entity matrix (mapped)", ""])
    lines.append("| Path | Platform | Read | Type | Enabled? | Status |")
    lines.append("|------|----------|------|------|----------|--------|")
    for row in report.get("entity_matrix") or []:
        if row.get("ha_platform") is None:
            continue
        lines.append(
            f"| `{row['grpc_path']}` | {row['ha_platform']} | "
            f"{row.get('read_source')} | {row.get('value_type')} | "
            f"{row.get('suggested_enabled_default')} | "
            f"{row.get('ha_status')} |"
        )

    lines.extend(
        [
            "",
            "## Seeds coverage (integration seed paths)",
            "",
            "| Path | Present | Notify-only |",
            "|------|---------|-------------|",
        ]
    )
    lines.extend(
        f"| `{row['path']}` | {row.get('present')} | {row.get('in_notify_only')} |"
        for row in diffs.get("seeds_coverage") or []
    )

    lines.extend(
        ["", "_Attach the JSON report for full values and capability schema._", ""]
    )
    return "\n".join(lines)
