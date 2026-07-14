"""Unit tests for device capability scrape report builders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
sys.path.insert(0, str(ROOT / "scripts" / "grpc"))

from device_scrape_report import (  # noqa: E402
    REPORT_SCHEMA_VERSION,
    build_capability_index,
    build_diff_sections,
    build_entity_matrix,
    build_full_report,
    build_hardware_profile,
    build_local_vs_seeds,
    flatten_seeds_states,
    integration_version,
    redact_report,
    render_markdown,
    report_filename_stem,
    value_type_of,
)

_FIXTURE_CAPABILITIES = {
    "capabilities": [
        {
            "name": "power",
            "type": "bool",
            "props": {"commands": ["set"], "get": True, "notify": True},
        },
        {
            "name": "sound_setting.night_mode",
            "type": "bool",
            "props": {"commands": ["set"], "get": True, "notify": True},
        },
        {
            "name": "sound_setting.drc",
            "type": "enum",
            "props": {
                "commands": ["set"],
                "get": False,
                "notify": False,
                "values": ["auto", "on", "off"],
            },
        },
        {
            "name": "sound_setting.volume.subwoofer",
            "type": "int",
            "props": {
                "commands": ["set"],
                "get": True,
                "notify": True,
                "min": -10,
                "max": 10,
            },
        },
        {
            "name": "sound_setting.volume.subwoofer.availability",
            "type": "bool",
            "props": {"commands": [], "get": True, "notify": True},
        },
        {
            "name": "speaker_connection_setting.connection_status.fl",
            "type": "enum",
            "props": {
                "commands": [],
                "get": True,
                "notify": True,
                "values": ["disconnected", "connected", "protected"],
            },
        },
        {
            "name": "system_setting.network_diagnostic_probe",
            "type": "enum",
            "props": {
                "commands": ["set"],
                "get": True,
                "notify": True,
                "values": ["auto", "on", "off"],
            },
        },
        {
            "name": "oobe_grpc.start",
            "type": "void",
            "props": {"commands": ["set"], "get": False, "notify": False},
        },
    ]
}

_FIXTURE_SNAPSHOT = {
    "system_setting.model_name": "HT-A9M2",
    "fw_update.version.main": "001.454",
    "system_setting.friendly_name": "Test Quad Speaker",
    "system_setting.serial_number": "SN000000",
    "system_setting.ipv4_address": "192.0.2.1",
    "system_setting.time_zone": "Etc/GMT+5|-300",
    "system_setting.wifi_mac_address_wired": "02:00:00:00:00:01",
    "power": True,
    "sound_setting.night_mode": False,
    "sound_setting.volume.subwoofer": 0,
    "sound_setting.volume.subwoofer.availability": True,
    "speaker_connection_setting.connection_status.fl": "connected",
    "speaker_connection_setting.connection_status.rl": "connected",
    "speaker_connection_setting.connection_status.rr": "connected",
    "speaker_connection_setting.connection_status.sw": "connected",
    "system_setting.auto_standby": True,
    "playback_control.title": "Secret Track",
    "playback_control.artist": "Secret Artist",
    "playback_control.album": "Secret Album",
    "playback_control.jacket_url": "https://example.invalid/cover.jpg",
    "playback_control.spotify_playlist_name": "Secret Playlist",
    "sound_optimization.sound_gps.speaker_location": '[{"0":{"x":1.0}}]',
}

_FIXTURE_SEEDS = {
    "sound_setting.drc": "auto",
    "system_setting.auto_standby": False,
    "system_setting.dimmer": "normal",
    "system_setting.ipv4_address": "192.0.2.1",
}


def test_build_capability_index() -> None:
    index = build_capability_index(_FIXTURE_CAPABILITIES)
    assert "power" in index
    assert index["power"].cap_get is True
    assert index["sound_setting.drc"].cap_set is True
    assert index["sound_setting.drc"].cap_get is False
    assert index["oobe_grpc.start"].cap_type == "void"


def test_flatten_seeds_states_name_value_pairs() -> None:
    payload = [
        {"name": "sound_setting.drc", "value": "auto"},
        {"name": "system_setting.dimmer", "value": "normal"},
    ]
    flat = flatten_seeds_states(payload)
    assert flat == {
        "sound_setting.drc": "auto",
        "system_setting.dimmer": "normal",
    }


def test_build_hardware_profile_subwoofer_and_topology() -> None:
    index = build_capability_index(_FIXTURE_CAPABILITIES)
    hw = build_hardware_profile(_FIXTURE_SNAPSHOT, index)
    assert hw["model_id"] == "HT-A9M2"
    assert hw["firmware"] == "001.454"
    assert hw["has_subwoofer"] is True
    assert hw["subwoofer_connected"] is True
    assert hw["has_rear_speakers"] is True
    assert hw["speaker_topology"]["fl"] == "connected"


def test_value_type_of() -> None:
    assert value_type_of(True) == "bool"
    assert value_type_of(3) == "int"
    assert value_type_of("auto") == "str"
    assert value_type_of(None) == "null"


def test_entity_matrix_mapped_and_seeds_read() -> None:
    index = build_capability_index(_FIXTURE_CAPABILITIES)
    hw = build_hardware_profile(_FIXTURE_SNAPSHOT, index)
    matrix = build_entity_matrix(
        cap_index=index,
        grpc_snapshot=_FIXTURE_SNAPSHOT,
        seeds_flat=_FIXTURE_SEEDS,
        hardware=hw,
    )
    by_path = {row["grpc_path"]: row for row in matrix}
    assert by_path["power"]["read_source"] == "local_grpc"
    assert by_path["power"]["value_type"] == "bool"
    assert by_path["power"]["suggested_enabled_default"] is True
    assert by_path["sound_setting.drc"]["read_source"] == "seeds_cloud"
    assert by_path["sound_setting.drc"]["value_type"] == "str"
    assert by_path["sound_setting.volume.subwoofer"]["device_gates"] == []
    assert (
        by_path["sound_setting.volume.subwoofer"]["suggested_enabled_default"] is True
    )
    assert (
        by_path["system_setting.network_diagnostic_probe"]["ha_status"]
        == "unmapped_new"
    )


def test_local_vs_seeds() -> None:
    section = build_local_vs_seeds(_FIXTURE_SNAPSHOT, _FIXTURE_SEEDS)
    assert "system_setting.auto_standby" in {row["path"] for row in section["unequal"]}
    assert section["unequal_count"] >= 1
    assert "system_setting.ipv4_address" in section["equal_paths"]


def test_build_diff_sections_counts() -> None:
    index = build_capability_index(_FIXTURE_CAPABILITIES)
    hw = build_hardware_profile(_FIXTURE_SNAPSHOT, index)
    matrix = build_entity_matrix(
        cap_index=index,
        grpc_snapshot=_FIXTURE_SNAPSHOT,
        seeds_flat=_FIXTURE_SEEDS,
        hardware=hw,
    )
    diffs = build_diff_sections(
        cap_index=index,
        grpc_snapshot=_FIXTURE_SNAPSHOT,
        seeds_flat=_FIXTURE_SEEDS,
        entity_matrix=matrix,
    )
    assert diffs["capability_path_count"] == len(index)
    assert diffs["entity_paths_with_live_value"] >= 1
    assert "system_setting.network_diagnostic_probe" in diffs["unmapped_new_candidates"]
    assert "local_vs_seeds" in diffs
    assert any(row.get("in_seeds_seed_paths") for row in diffs["seeds_coverage"])


def test_build_full_report_and_redact() -> None:
    report = build_full_report(
        host="10.0.0.1",
        auth_gate={"auth_ok": True},
        capabilities_raw={"ok": True, "latency_s": 0.01},
        capabilities_json=_FIXTURE_CAPABILITIES,
        grpc_snapshot={
            k: v
            for k, v in _FIXTURE_SNAPSHOT.items()
            if k != "system_setting.model_name"
        },
        seeds_flat=_FIXTURE_SEEDS,
        seeds_latency_ms=42.0,
        scrape_meta={"grpc_bulk_fields": 10},
        tcp_reachable={"reachable": True, "port": 33336, "error": None},
        http_identity={"ok": True, "model_id": "HT-A9M2", "firmware": "001.454"},
    )
    assert report["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert report["integration_version"] == integration_version()
    assert report["hardware_profile"]["model_id"] == "HT-A9M2"
    assert report["tcp_reachable"]["reachable"] is True
    assert len(report["entity_matrix"]) > 0

    redacted = redact_report(report, include_pii=False)
    assert redacted["host"] == "[redacted]"
    assert redacted["hardware_profile"]["serial"] == "[redacted]"
    assert redacted["grpc_snapshot"]["system_setting.serial_number"] == "[redacted]"
    assert redacted["grpc_snapshot"]["system_setting.ipv4_address"] == "[redacted]"
    assert redacted["grpc_snapshot"]["system_setting.time_zone"] == "[redacted]"
    assert (
        redacted["grpc_snapshot"]["system_setting.wifi_mac_address_wired"]
        == "[redacted]"
    )
    assert redacted["seeds"]["flat"]["system_setting.ipv4_address"] == "[redacted]"
    assert redacted["grpc_snapshot"]["playback_control.title"] == "[redacted]"
    assert redacted["grpc_snapshot"]["playback_control.artist"] == "[redacted]"
    assert redacted["grpc_snapshot"]["playback_control.album"] == "[redacted]"
    assert redacted["grpc_snapshot"]["playback_control.jacket_url"] == "[redacted]"
    assert (
        redacted["grpc_snapshot"]["playback_control.spotify_playlist_name"]
        == "[redacted]"
    )
    assert (
        redacted["grpc_snapshot"]["sound_optimization.sound_gps.speaker_location"]
        == "[redacted]"
    )
    # Non-PII playback fields stay visible for quirk analysis.
    assert redacted["grpc_snapshot"]["power"] is True
    ip_row = next(
        row
        for row in redacted["entity_matrix"]
        if row["grpc_path"] == "system_setting.ipv4_address"
    )
    assert ip_row["live_value"] == "[redacted]"
    tz_row = next(
        row
        for row in redacted["entity_matrix"]
        if row["grpc_path"] == "system_setting.time_zone"
    )
    assert tz_row["live_value"] == "[redacted]"

    md = render_markdown(redacted)
    assert "HT-A9M2" in md
    assert "Entity matrix" in md
    assert "Report schema" in md
    assert "TCP :33336 reachable" in md


def test_report_filename_stem() -> None:
    stem = report_filename_stem(
        {"model_id": "HT-A9M2", "firmware": "001.454"},
        timestamp="20260707-120000",
    )
    assert stem == "device-scrape-HT-A9M2-001.454-20260707-120000"


def test_fixture_from_investigation_capabilities_json() -> None:
    """Optional: load trimmed HT-A9M2 capabilities if investigation report exists."""
    inv_report = (
        ROOT.parent
        / "bravia-quad-investigation"
        / "reports"
        / "grpc-capabilities-20260707.json"
    )
    if not inv_report.is_file():
        return
    payload = json.loads(inv_report.read_text(encoding="utf-8"))
    cap_json = payload.get("capabilities_json")
    assert isinstance(cap_json, dict)
    index = build_capability_index(cap_json)
    assert len(index) > 100
    assert "power" in index
    assert "sound_setting.night_mode" in index
