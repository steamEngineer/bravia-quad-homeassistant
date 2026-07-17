"""Tests for gRPC mapping and key loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.bravia_quad.const import (
    CONF_GRPC_KEYS,
    CONF_USE_GRPC,
    DEFAULT_GRPC_PORT,
    FEATURE_AAV,
    FEATURE_DRC,
    FEATURE_POWER,
)
from custom_components.bravia_quad.grpc.client import load_keys_from_file
from custom_components.bravia_quad.grpc_mapping import (
    GRPC_TCP_MAPPINGS,
    PARITY_GATE_COMMANDS,
    mappings_for_platform,
)


def test_grpc_port_default() -> None:
    """gRPC uses h2c port 55051."""
    assert DEFAULT_GRPC_PORT == 55051


def test_parity_gate_includes_power() -> None:
    """Parity gate covers power."""
    paths = {row[0] for row in PARITY_GATE_COMMANDS}
    assert "power" in paths
    assert any(
        m.grpc_path == "power" and m.tcp_feature == FEATURE_POWER
        for m in GRPC_TCP_MAPPINGS
    )


def test_load_keys_from_example(tmp_path: Path) -> None:
    """Keys file loader accepts example JSON shape."""
    example = {
        "device_id": "00000000-0000-0000-0000-000000000001",
        "key_id": "f4c726b3-e80d-4b7f-9c3a-33a5a86f5540",
        "session_key": "a" * 64,
        "hmac_key": "b" * 64,
        "expires_in": 86400,
    }
    path = tmp_path / "keys.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    loaded = load_keys_from_file(str(path))
    assert loaded["device_id"] == example["device_id"]
    assert loaded["session_key"] == example["session_key"]


def test_load_keys_missing_required(tmp_path: Path) -> None:
    """Keys file must include session_key and hmac_key."""
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required fields"):
        load_keys_from_file(str(path))


def test_config_option_keys() -> None:
    """Option keys are stable."""
    assert CONF_USE_GRPC == "use_grpc"
    assert CONF_GRPC_KEYS == "grpc_keys"


def test_drc_path_not_dts_dialog_control() -> None:
    drc = next(m for m in GRPC_TCP_MAPPINGS if m.tcp_feature == FEATURE_DRC)
    assert drc.grpc_path == "sound_setting.drc"


def test_aav_on_auto_volume_path() -> None:
    aav = next(m for m in GRPC_TCP_MAPPINGS if m.tcp_feature == FEATURE_AAV)
    assert aav.grpc_path == "sound_setting.auto_volume"
    assert aav.ha_platform == "switch"


def test_dual_mono_is_select() -> None:
    dual = next(
        m for m in GRPC_TCP_MAPPINGS if m.grpc_path == "sound_setting.dual_mono"
    )
    assert dual.ha_platform == "select"


def test_bt_quality_is_writable_select() -> None:
    bt = next(
        m
        for m in GRPC_TCP_MAPPINGS
        if m.grpc_path == "bluetooth_setting.connection_quality"
    )
    assert bt.ha_platform == "select"
    assert bt.writable is True


def test_parity_gate_includes_drc_and_aav() -> None:
    paths = {row[0] for row in PARITY_GATE_COMMANDS}
    assert "sound_setting.drc" in paths
    assert "sound_setting.auto_volume" in paths


def test_notify_only_grpc_paths_defined() -> None:
    from custom_components.bravia_quad.grpc_mapping import NOTIFY_ONLY_GRPC_PATHS

    assert "sound_setting.drc" in NOTIFY_ONLY_GRPC_PATHS
    assert "speaker_sound_setting.360ssm_height" in NOTIFY_ONLY_GRPC_PATHS


def test_grpc_path_needs_ha_restore() -> None:
    from custom_components.bravia_quad.grpc_mapping import grpc_path_needs_ha_restore

    assert grpc_path_needs_ha_restore("sound_setting.drc") is True
    assert grpc_path_needs_ha_restore("sound_setting.dsee_ultimate") is True
    assert grpc_path_needs_ha_restore("system_setting.dimmer") is True
    assert grpc_path_needs_ha_restore("system_setting.hdmi_signal_format") is True
    assert grpc_path_needs_ha_restore("sound_setting.dts_dialog_control") is True
    assert (
        grpc_path_needs_ha_restore("speaker_sound_setting.center_speaker_mode") is True
    )
    assert grpc_path_needs_ha_restore("sound_setting.night_mode") is False
    assert grpc_path_needs_ha_restore("power") is False


def test_ipv4_address_mapped_as_sensor() -> None:
    paths = {m.grpc_path for m in mappings_for_platform("sensor", writable=False)}
    assert "system_setting.ipv4_address" in paths
