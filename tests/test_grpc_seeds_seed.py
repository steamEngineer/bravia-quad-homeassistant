"""Tests for Sony Seeds cloud entity seeding."""

from __future__ import annotations

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
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
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


def test_seeds_seed_paths_cover_notify_only_and_sound_effect() -> None:
    assert "sound_setting.drc" in SEEDS_SEED_PATHS
    assert "system_setting.dimmer" in SEEDS_SEED_PATHS
    assert "sound_setting.sound_effect" in SEEDS_SEED_PATHS
    assert len(SEEDS_SEED_PATHS) == 11
