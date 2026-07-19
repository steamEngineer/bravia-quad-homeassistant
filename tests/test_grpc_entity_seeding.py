"""Tests for gRPC entity path seeding and None-safe dispatch."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync
from custom_components.bravia_quad.grpc.get_states_response import (
    parse_get_states_response,
)
from custom_components.bravia_quad.grpc_mapping import (
    GRPC_TCP_MAPPINGS,
    entity_critical_grpc_paths,
    mappings_for_tcp_seed,
    missing_entity_paths,
    notify_only_mappings_with_tcp,
)
from custom_components.bravia_quad.grpc_tcp_seed import async_seed_notify_only_from_tcp
from custom_components.bravia_quad.grpc_value_normalize import (
    coerce_bool,
)
from tests.conftest import frida_fixture_dir

if TYPE_CHECKING:
    from custom_components.bravia_quad.grpc.client import NotifyStateUpdate


def test_entity_critical_paths_include_media_player_and_handcrafted() -> None:
    paths = entity_critical_grpc_paths()
    assert "power" in paths
    assert "mute" in paths
    assert "sound_setting.sound_effect" in paths
    assert "sound_setting.drc" in paths
    assert "sound_setting.sound_field.availability" not in paths


def test_filter_field_paths_keeps_metadata_for_advertised_base() -> None:
    from custom_components.bravia_quad.grpc.get_capabilities_response import (
        filter_field_paths,
    )

    ha_paths = [
        "sound_setting.voice_zoom.on_off",
        "sound_setting.voice_zoom.availability",
        "sound_setting.voice_zoom.unavailable_reason",
        "power",
    ]
    caps = frozenset({"sound_setting.voice_zoom.on_off", "power"})
    filtered = filter_field_paths(ha_paths, caps)
    assert "sound_setting.voice_zoom.availability" in filtered
    assert "sound_setting.voice_zoom.unavailable_reason" in filtered
    assert "sound_setting.voice_zoom.on_off" in filtered


def test_missing_entity_paths_treats_none_as_unset() -> None:
    state = {"power": True, "mute": None, "volume": 34}
    missing = missing_entity_paths(state)
    assert "power" not in missing
    assert "mute" in missing
    assert "volume" not in missing


def test_missing_entity_paths_omits_paths_absent_from_caps() -> None:
    """Quad-like caps: A8-only mapped paths are not counted missing."""
    caps = frozenset({"power", "mute", "volume"})
    missing = missing_entity_paths({}, caps)
    assert "battery.life.rl" not in missing
    assert "sound_setting.mix_stage" not in missing
    assert "sound_setting.stereo_playback" not in missing
    assert "speaker_sound_setting.sw_phase" not in missing
    assert "power" in missing
    # Notify-only paths stay allowed even when absent from caps.
    assert "sound_setting.drc" in missing


def test_coerce_bool_none_stays_none() -> None:
    assert coerce_bool(None) is None
    assert coerce_bool(True) is True
    assert coerce_bool("off") is False
    assert coerce_bool("upon") is True


def test_frida_snapshot_none_entity_paths() -> None:
    capture = frida_fixture_dir() / "getstates_rx_seq51.bin"
    if not capture.is_file():
        pytest.skip("Frida capture not available")
    result = parse_get_states_response(capture.read_bytes())
    none_paths = {
        "mute",
        "sound_setting.night_mode",
        "sound_setting.sound_field",
        "sound_setting.voice_mode",
        "sound_setting.dts_dialog_control",
    }
    for path in none_paths:
        assert path in result
        assert result[path] is None


@pytest.mark.asyncio
async def test_fetch_field_paths_skips_notify_only_even_when_none() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._client._notify_state = {
        "power": True,
        "sound_setting.drc": None,
    }

    with patch.object(client._client, "get_states_single_path") as mock_single:
        resolved = await client.async_fetch_field_paths(["sound_setting.drc"])

    mock_single.assert_not_called()
    assert resolved == 0


@pytest.mark.asyncio
async def test_backfill_entity_paths_resolves_bulk_only() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._client._notify_state = {
        "power": True,
        "sound_setting.night_mode": None,
    }

    def _single_path(path: str, **kwargs: object) -> dict[str, object] | None:
        if path == "sound_setting.night_mode":
            return {"sound_setting.night_mode": True}
        return None

    with (
        patch.object(
            client._client, "get_states_single_path", side_effect=_single_path
        ) as mock_single,
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=0),
        ),
    ):
        bulk_r, notify_r, still = await client.async_backfill_entity_paths()

    assert bulk_r == 1
    assert notify_r == 0
    mock_single.assert_any_call(
        "sound_setting.night_mode",
        use_signed_auth=True,
        quiet=True,
    )
    assert client.notify_state["sound_setting.night_mode"] is True
    assert still < len(entity_critical_grpc_paths())


@pytest.mark.asyncio
async def test_dispatch_snapshot_callbacks_skip_none() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._client._notify_state = {
        "sound_setting.night_mode": None,
        "power": True,
    }
    received: list[NotifyStateUpdate] = []

    def _cb(update: NotifyStateUpdate) -> None:
        received.append(update)

    client.add_state_callback(_cb)
    client.dispatch_snapshot_callbacks()

    assert len(received) == 1
    assert received[0].path == "power"


@pytest.mark.asyncio
async def test_warmup_notify_waits_for_missing_paths() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._client._notify_state = {"power": True}

    async def _fill_later() -> None:
        await asyncio.sleep(0.1)
        client._client._notify_state["mute"] = False

    fill_task = asyncio.create_task(_fill_later())
    still = await client.async_warmup_notify(
        missing_paths=frozenset({"mute"}),
        timeout=1.0,
    )
    await fill_task

    assert still == frozenset()
    assert client.notify_state["mute"] is False


def test_notify_only_mappings_with_tcp_covers_seven_paths() -> None:
    mappings = notify_only_mappings_with_tcp()
    paths = {m.grpc_path for m in mappings}
    assert paths == {
        "sound_setting.drc",
        "sound_setting.auto_volume",
        "system_setting.earc",
        "system_setting.hdmi_standby_through",
        "system_setting.auto_standby",
        "system_setting.auto_update",
        "system_setting.external_control",
    }
    assert all(m.tcp_feature is not None for m in mappings)


@pytest.mark.asyncio
async def test_tcp_seed_fills_notify_only_drc() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    grpc._client._notify_state = {"sound_setting.drc": None}

    async def _get(feature: str) -> str | None:
        if feature == "audio.drangecomp":
            return "auto"
        return None

    mock_tcp = MagicMock()
    mock_tcp.async_connect = AsyncMock()
    mock_tcp.async_disconnect = AsyncMock()
    mock_tcp.async_get_tcp_feature = AsyncMock(side_effect=_get)

    with patch(
        "custom_components.bravia_quad.grpc_tcp_seed.BraviaQuadClient",
        return_value=mock_tcp,
    ):
        seeded = await async_seed_notify_only_from_tcp("10.0.0.1", grpc)

    assert seeded == 1
    assert grpc.notify_state["sound_setting.drc"] == "auto"
    mock_tcp.async_connect.assert_awaited_once()
    mock_tcp.async_disconnect.assert_awaited_once()


def test_mappings_for_tcp_seed_includes_getstates_gaps() -> None:
    state = {
        "sound_setting.drc": "auto",
        "sound_setting.night_mode": None,
        "sound_setting.voice_mode": None,
        "sound_setting.voice_zoom.on_off": None,
    }
    paths = {m.grpc_path for m in mappings_for_tcp_seed(state)}
    assert "sound_setting.night_mode" in paths
    assert "sound_setting.voice_mode" in paths
    assert "sound_setting.voice_zoom.on_off" in paths
    assert "sound_setting.drc" not in paths


@pytest.mark.asyncio
async def test_tcp_seed_skips_paths_already_set() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    critical = entity_critical_grpc_paths()
    grpc._client._notify_state = {
        mapping.grpc_path: True
        for mapping in GRPC_TCP_MAPPINGS
        if mapping.tcp_feature is not None and mapping.grpc_path in critical
    }

    mock_tcp = MagicMock()
    mock_tcp.async_connect = AsyncMock()
    mock_tcp.async_disconnect = AsyncMock()
    mock_tcp.async_get_tcp_feature = AsyncMock(return_value="auto")

    with patch(
        "custom_components.bravia_quad.grpc_tcp_seed.BraviaQuadClient",
        return_value=mock_tcp,
    ):
        seeded = await async_seed_notify_only_from_tcp("10.0.0.1", grpc)

    assert seeded == 0
    mock_tcp.async_connect.assert_not_called()
    mock_tcp.async_get_tcp_feature.assert_not_called()


@pytest.mark.asyncio
async def test_tcp_seed_returns_zero_when_connect_fails() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    grpc._client._notify_state = {"sound_setting.drc": None}

    mock_tcp = MagicMock()
    mock_tcp.async_connect = AsyncMock(side_effect=ConnectionError("refused"))

    with patch(
        "custom_components.bravia_quad.grpc_tcp_seed.BraviaQuadClient",
        return_value=mock_tcp,
    ):
        seeded = await async_seed_notify_only_from_tcp("10.0.0.1", grpc)

    assert seeded == 0
    assert grpc.notify_state["sound_setting.drc"] is None


@pytest.mark.asyncio
async def test_backfill_entity_paths_tcp_seeds_notify_only() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._client._notify_state = {"power": True, "sound_setting.drc": None}

    with (
        patch.object(client._client, "get_states_single_path", return_value=None),
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=2),
        ) as mock_tcp_seed,
    ):
        bulk_r, notify_r, still = await client.async_backfill_entity_paths()

    mock_tcp_seed.assert_awaited_once_with("10.0.0.1", client)
    assert bulk_r == 0
    assert notify_r == 2
    assert still < len(entity_critical_grpc_paths())
