"""Tests for Sony Seeds cloud entity seeding."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync
from custom_components.bravia_quad.grpc_seeds_seed import (
    SEEDS_SEED_PATHS,
    async_seed_from_seeds,
    parse_seeds_device_states,
)


def test_parse_seeds_device_states_name_value_array() -> None:
    raw = {
        "states": [
            {"name": "sound_setting.drc", "value": "auto"},
            {"name": "sound_setting.dsee_ultimate", "value": False},
        ]
    }
    assert parse_seeds_device_states(raw) == {
        "sound_setting.drc": "auto",
        "sound_setting.dsee_ultimate": False,
    }


def test_parse_seeds_device_states_empty() -> None:
    assert parse_seeds_device_states({}) == {}
    assert parse_seeds_device_states({"states": "bad"}) == {}


@pytest.mark.asyncio
async def test_seed_from_seeds_fills_unset_paths() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    grpc._client._notify_state = {
        "sound_setting.drc": None,
        "sound_setting.dsee_ultimate": None,
        "sound_setting.night_mode": True,
    }
    credentials = {"device_id": "d", "access_token": "tok"}
    hass = MagicMock()
    raw = {
        "states": [
            {"name": "sound_setting.drc", "value": "off"},
            {"name": "sound_setting.dsee_ultimate", "value": True},
            {"name": "sound_setting.night_mode", "value": False},
        ]
    }

    with patch(
        "custom_components.bravia_quad.grpc_seeds_seed.async_get_device_states",
        new=AsyncMock(return_value=raw),
    ):
        seeded = await async_seed_from_seeds(hass, credentials, grpc)

    assert seeded == 2
    assert grpc.notify_state["sound_setting.drc"] == "off"
    assert grpc.notify_state["sound_setting.dsee_ultimate"] is True
    assert grpc.notify_state["sound_setting.night_mode"] is True


@pytest.mark.asyncio
async def test_seed_from_seeds_fills_empty_wire_bools() -> None:
    """Empty-wire GetStates bools are seeded from Seeds when unset."""
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    grpc._client._notify_state = {
        "sound_setting.voice_mode": None,
        "sound_setting.night_mode": None,
        "sound_setting.sound_field": None,
    }
    credentials = {"device_id": "d", "access_token": "tok"}
    raw = {
        "states": [
            {"name": "sound_setting.voice_mode", "value": False},
            {"name": "sound_setting.night_mode", "value": True},
            {"name": "sound_setting.sound_field", "value": False},
        ]
    }

    with (
        patch(
            "custom_components.bravia_quad.grpc_seeds_seed.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.bravia_quad.grpc_seeds_seed.async_get_device_states",
            new=AsyncMock(return_value=raw),
        ),
    ):
        seeded = await async_seed_from_seeds(MagicMock(), credentials, grpc)

    assert seeded == 3
    assert grpc.notify_state["sound_setting.voice_mode"] is False
    assert grpc.notify_state["sound_setting.night_mode"] is True
    assert grpc.notify_state["sound_setting.sound_field"] is False


@pytest.mark.asyncio
async def test_seed_from_seeds_skips_without_token() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1")
    grpc._client._notify_state = {"sound_setting.drc": None}
    seeded = await async_seed_from_seeds(MagicMock(), {}, grpc)
    assert seeded == 0


@pytest.mark.asyncio
async def test_backfill_uses_seeds_not_tcp_when_enabled() -> None:
    client = BraviaGrpcClientAsync(
        "10.0.0.1",
        device_id="d",
        key_id="k",
        seeds_poll=True,
        credentials={"access_token": "tok", "device_id": "d"},
        hass=MagicMock(),
    )
    client._connected = True
    client._tcp_reachable = False
    client._client._notify_state = {"sound_setting.drc": None}

    with (
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
            new=AsyncMock(return_value=1),
        ) as mock_seeds,
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=0),
        ) as mock_tcp,
    ):
        _bulk_r, notify_r, _still = await client.async_backfill_entity_paths()

    mock_seeds.assert_awaited_once()
    mock_tcp.assert_not_awaited()
    assert notify_r == 1


@pytest.mark.asyncio
async def test_backfill_uses_tcp_when_seeds_disabled() -> None:
    """Unknown tcp_reachable (None) still tries TCP seed — legacy soft-fail."""
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    assert client._tcp_reachable is None
    client._client._notify_state = {}

    with (
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
            new=AsyncMock(return_value=0),
        ) as mock_seeds,
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=2),
        ) as mock_tcp,
    ):
        await client.async_backfill_entity_paths()

    mock_seeds.assert_not_awaited()
    mock_tcp.assert_awaited_once()


@pytest.mark.asyncio
async def test_backfill_uses_tcp_when_tcp_reachable() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._tcp_reachable = True
    client._client._notify_state = {}

    with (
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
            new=AsyncMock(return_value=0),
        ) as mock_seeds,
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=2),
        ) as mock_tcp,
    ):
        _bulk_r, notify_r, _still = await client.async_backfill_entity_paths()

    mock_seeds.assert_not_awaited()
    mock_tcp.assert_awaited_once()
    assert notify_r == 2


@pytest.mark.asyncio
async def test_backfill_skips_tcp_seed_when_tcp_unreachable() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._tcp_reachable = False
    client._client._notify_state = {}

    with (
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
            new=AsyncMock(return_value=0),
        ) as mock_seeds,
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=2),
        ) as mock_tcp,
    ):
        _bulk_r, notify_r, _still = await client.async_backfill_entity_paths()

    mock_seeds.assert_not_awaited()
    mock_tcp.assert_not_awaited()
    assert notify_r == 0


@pytest.mark.asyncio
async def test_backfill_logs_seeds_hint_once_when_tcp_down() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._tcp_reachable = False
    client._client._notify_state = {}

    with (
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_notify_only_from_tcp",
            new=AsyncMock(return_value=0),
        ),
        patch("custom_components.bravia_quad.bravia_grpc_client._LOGGER") as mock_log,
    ):
        await client.async_backfill_entity_paths()
        await client.async_backfill_entity_paths()

    info_msgs = [
        call.args[0]
        for call in mock_log.info.call_args_list
        if call.args and "Seeds cloud reads" in call.args[0]
    ]
    assert len(info_msgs) == 1


def test_note_external_control_ensure_sets_tcp_reachable() -> None:
    from custom_components.bravia_quad.external_control import (
        ExternalControlEnsureResult,
    )

    client = BraviaGrpcClientAsync("10.0.0.1")
    assert client._tcp_reachable is None
    client.note_external_control_ensure(
        ExternalControlEnsureResult(
            was_already_on=False,
            enabled_via="grpc",
            tcp_reachable=False,
            external_control_on=True,
        )
    )
    assert client._tcp_reachable is False


def test_seeds_seed_paths_cover_notify_only_and_sound_effect() -> None:
    assert "sound_setting.drc" in SEEDS_SEED_PATHS
    assert "system_setting.dimmer" in SEEDS_SEED_PATHS
    assert "sound_setting.sound_effect" in SEEDS_SEED_PATHS
    assert "sound_setting.voice_mode" in SEEDS_SEED_PATHS
    assert "sound_setting.night_mode" in SEEDS_SEED_PATHS
    assert len(SEEDS_SEED_PATHS) == 15


@pytest.mark.asyncio
async def test_seed_from_seeds_force_overwrites_set_paths() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    grpc._client._notify_state = {
        "sound_setting.drc": "auto",
        "sound_setting.auto_volume": True,
    }
    credentials = {"device_id": "d", "access_token": "tok"}
    raw = {
        "states": [
            {"name": "sound_setting.drc", "value": "off"},
            {"name": "sound_setting.auto_volume", "value": False},
        ]
    }

    with (
        patch(
            "custom_components.bravia_quad.grpc_seeds_seed.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.bravia_quad.grpc_seeds_seed.async_get_device_states",
            new=AsyncMock(return_value=raw),
        ),
    ):
        forced = await async_seed_from_seeds(MagicMock(), credentials, grpc, force=True)
        skipped = await async_seed_from_seeds(MagicMock(), credentials, grpc)

    assert forced == 2
    assert grpc.notify_state["sound_setting.drc"] == "off"
    assert grpc.notify_state["sound_setting.auto_volume"] is False
    assert skipped == 0


@pytest.mark.asyncio
async def test_seed_from_seeds_force_skips_unchanged() -> None:
    grpc = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    grpc._client._notify_state = {"sound_setting.drc": "auto"}
    credentials = {"device_id": "d", "access_token": "tok"}
    raw = {"states": [{"name": "sound_setting.drc", "value": "auto"}]}

    with (
        patch(
            "custom_components.bravia_quad.grpc_seeds_seed.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.bravia_quad.grpc_seeds_seed.async_get_device_states",
            new=AsyncMock(return_value=raw),
        ) as mock_get,
    ):
        seeded = await async_seed_from_seeds(MagicMock(), credentials, grpc, force=True)

    mock_get.assert_awaited_once()
    assert seeded == 0


@pytest.mark.asyncio
async def test_exec_command_skips_post_exec_seeds_and_guards_path() -> None:
    """HA writes must not immediately force-refresh Seeds (stale cloud revert)."""
    client = BraviaGrpcClientAsync(
        "10.0.0.1",
        device_id="d",
        key_id="k",
        seeds_poll=True,
        credentials={"access_token": "tok", "device_id": "d"},
        hass=MagicMock(),
    )
    client._connected = True
    client._client._notify_state = {"sound_setting.drc": "off"}

    with (
        patch.object(client._client, "exec_command", return_value=True),
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
            new=AsyncMock(return_value=1),
        ) as mock_seeds,
    ):
        ok = await client.async_exec_command("sound_setting.drc", string_value="off")

    assert ok is True
    mock_seeds.assert_not_awaited()
    assert "sound_setting.drc" in client._seeds_guarded_paths()


@pytest.mark.asyncio
async def test_schedule_seeds_refresh_noop_when_seeds_poll_off() -> None:
    client = BraviaGrpcClientAsync(
        "10.0.0.1",
        seeds_poll=False,
        credentials={"access_token": "tok", "device_id": "d"},
        hass=MagicMock(),
    )
    with patch(
        "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
        new=AsyncMock(return_value=0),
    ) as mock_seeds:
        client.schedule_seeds_refresh()
        await asyncio.sleep(0)

    assert client._seeds_refresh_task is None
    mock_seeds.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_audio_debounces_to_single_seeds_force_refresh() -> None:
    client = BraviaGrpcClientAsync(
        "10.0.0.1",
        seeds_poll=True,
        credentials={"access_token": "tok", "device_id": "d"},
        hass=MagicMock(),
    )
    client._client._notify_state = {"sound_setting.drc": "auto"}
    dispatched: list[str] = []
    client.add_state_callback(lambda update: dispatched.append(update.path))

    with (
        patch(
            "custom_components.bravia_quad.bravia_grpc_client.async_seed_from_seeds",
            new=AsyncMock(return_value=1),
        ) as mock_seeds,
        patch(
            "custom_components.bravia_quad.bravia_grpc_client._SEEDS_NO_AUDIO_DEBOUNCE_S",
            0.05,
        ),
    ):
        client.schedule_seeds_refresh()
        client.schedule_seeds_refresh()
        await asyncio.sleep(0.15)

    mock_seeds.assert_awaited_once()
    assert mock_seeds.await_args.kwargs["force"] is True
    assert "sound_setting.drc" in dispatched
