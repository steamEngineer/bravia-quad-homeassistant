"""Tests for gRPC auto-reconnect when the notify stream drops."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync

if TYPE_CHECKING:
    from custom_components.bravia_quad.grpc.client import NotifyStateUpdate


@pytest.fixture(autouse=True)
def _mock_ensure_external_control() -> None:
    with patch(
        "custom_components.bravia_quad.bravia_grpc_client.async_ensure_external_control_enabled",
        new=AsyncMock(),
    ):
        yield


@pytest.fixture
def grpc_async() -> BraviaGrpcClientAsync:
    client = BraviaGrpcClientAsync(
        "192.168.1.50",
        device_id="dev",
        key_id="kid",
        session_key="s" * 64,
        hmac_key="h" * 64,
    )
    client._connected = True
    client._client._notify_state = {"main.power": True}
    return client


async def test_reconnects_after_notify_stream_ends(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    """When StartNotifyStates ends, the manager should restore the session."""
    stream_calls = 0

    def fake_notify() -> Iterator[NotifyStateUpdate]:
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls == 1:
            return iter(())
        grpc_async._notify_stop.set()
        return iter(())

    grpc_async._client.start_notify_states = fake_notify
    grpc_async._client.disconnect = MagicMock()
    grpc_async.async_connect = AsyncMock(return_value=True)
    grpc_async.async_fetch_capabilities = AsyncMock(return_value=frozenset({"power"}))
    grpc_async.async_seed_notify_from_snapshot = AsyncMock(return_value=3)

    with patch.object(grpc_async, "_async_wait", new=AsyncMock()):
        await grpc_async.async_start_notify()
        await asyncio.wait_for(grpc_async._notify_task, timeout=2.0)

    grpc_async.async_connect.assert_awaited()
    grpc_async.async_seed_notify_from_snapshot.assert_awaited()
    assert stream_calls == 2


async def test_reconnect_callback_and_snapshot_callbacks(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    """Successful reconnect should refresh HA callbacks from cached notify_state."""
    updates: list[NotifyStateUpdate] = []

    def capture(update: NotifyStateUpdate) -> None:
        updates.append(update)

    grpc_async.add_state_callback(capture)
    reconnect_cb = AsyncMock()
    grpc_async.set_reconnect_callback(reconnect_cb)

    stream_calls = 0

    def fake_notify() -> Iterator[NotifyStateUpdate]:
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls >= 2:
            grpc_async._notify_stop.set()
        return iter(())

    grpc_async._client.start_notify_states = fake_notify
    grpc_async._client.disconnect = MagicMock()
    grpc_async.async_connect = AsyncMock(return_value=True)
    grpc_async.async_fetch_capabilities = AsyncMock(return_value=frozenset({"power"}))
    grpc_async.async_seed_notify_from_snapshot = AsyncMock(return_value=1)

    with patch.object(grpc_async, "_async_wait", new=AsyncMock()):
        await grpc_async.async_start_notify()
        await asyncio.wait_for(grpc_async._notify_task, timeout=2.0)

    reconnect_cb.assert_awaited_once()
    assert any(u.path == "main.power" for u in updates)


async def test_disconnect_stops_connection_manager(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    """Intentional shutdown should not keep retrying reconnect."""
    grpc_async._client.start_notify_states = lambda: iter(())

    with patch.object(grpc_async, "_async_wait", new=AsyncMock()):
        await grpc_async.async_start_notify()
        await grpc_async.async_disconnect()

    assert grpc_async._notify_task is None
    assert not grpc_async.is_connected
