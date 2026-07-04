"""Tests for per-path supplemental GetStates fetch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync
from custom_components.bravia_quad.grpc_mapping import NOTIFY_ONLY_GRPC_PATHS


@pytest.mark.asyncio
async def test_fetch_field_paths_skips_notify_only_paths() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True

    with patch.object(client._client, "get_states_single_path") as mock_single:
        count = await client.async_fetch_field_paths(list(NOTIFY_ONLY_GRPC_PATHS[:3]))

    mock_single.assert_not_called()
    assert count == 0


@pytest.mark.asyncio
async def test_fetch_field_paths_uses_single_path_requests() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._client._notify_state = {"power": True}

    with patch.object(
        client._client,
        "get_states_single_path",
        return_value={"sound_setting.night_mode": True},
    ) as mock_single:
        count = await client.async_fetch_field_paths(["sound_setting.night_mode"])

    mock_single.assert_called_once_with(
        "sound_setting.night_mode",
        use_signed_auth=True,
        quiet=True,
    )
    assert count == 1
    assert client.notify_state["sound_setting.night_mode"] is True


@pytest.mark.asyncio
async def test_fetch_field_paths_skips_resolved_values() -> None:
    client = BraviaGrpcClientAsync("10.0.0.1", device_id="d", key_id="k")
    client._connected = True
    client._client._notify_state = {
        "sound_setting.night_mode": True,
        "sound_setting.voice_mode": None,
    }

    with patch.object(
        client._client,
        "get_states_single_path",
        return_value={"sound_setting.voice_mode": False},
    ) as mock_single:
        count = await client.async_fetch_field_paths(
            ["sound_setting.night_mode", "sound_setting.voice_mode"]
        )

    assert count == 1
    mock_single.assert_called_once_with(
        "sound_setting.voice_mode",
        use_signed_auth=True,
        quiet=True,
    )
