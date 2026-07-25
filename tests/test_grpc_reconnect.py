"""Tests for gRPC auto-reconnect when the notify stream drops."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync

if TYPE_CHECKING:
    from collections.abc import Callable

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


def _fake_start_notify_factory(
    *,
    lose_after: int = 1,
    stop_client: BraviaGrpcClientAsync | None = None,
) -> Any:
    """Return a start_notify that signals connection_lost after *lose_after* starts."""
    calls = {"n": 0}

    def fake_start_notify(
        on_delta: Callable[[str, Any], None],
        on_connection_lost: Callable[[], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        del on_delta, on_reconnect
        calls["n"] += 1
        if calls["n"] >= lose_after and on_connection_lost is not None:
            on_connection_lost()
            if stop_client is not None and calls["n"] >= 2:
                stop_client._notify_stop.set()
                stop_client._notify_restore_event.set()

    fake_start_notify.calls = calls  # type: ignore[attr-defined]
    return fake_start_notify


async def test_reconnects_after_notify_stream_ends(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    """When notify connection_lost fires, the manager should restore the session."""
    fake_start = _fake_start_notify_factory(lose_after=1, stop_client=grpc_async)
    grpc_async._client.start_notify = fake_start  # type: ignore[method-assign]
    grpc_async._client.stop_notify = MagicMock()
    grpc_async._client.close = MagicMock()
    grpc_async.async_connect = AsyncMock(return_value=True)
    grpc_async.async_fetch_capabilities = AsyncMock(return_value=frozenset({"power"}))
    grpc_async.async_seed_notify_from_snapshot = AsyncMock(return_value=3)
    grpc_async.async_backfill_entity_paths = AsyncMock(return_value=(0, 0, 0))

    with patch.object(grpc_async, "_async_wait", new=AsyncMock()):
        await grpc_async.async_start_notify()
        await asyncio.wait_for(grpc_async._notify_task, timeout=2.0)

    grpc_async.async_connect.assert_awaited()
    grpc_async.async_seed_notify_from_snapshot.assert_awaited()
    assert fake_start.calls["n"] >= 2


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

    fake_start = _fake_start_notify_factory(lose_after=1, stop_client=grpc_async)
    grpc_async._client.start_notify = fake_start  # type: ignore[method-assign]
    grpc_async._client.stop_notify = MagicMock()
    grpc_async._client.close = MagicMock()
    grpc_async.async_connect = AsyncMock(return_value=True)
    grpc_async.async_fetch_capabilities = AsyncMock(return_value=frozenset({"power"}))
    grpc_async.async_seed_notify_from_snapshot = AsyncMock(return_value=1)
    grpc_async.async_backfill_entity_paths = AsyncMock(return_value=(0, 0, 0))

    with patch.object(grpc_async, "_async_wait", new=AsyncMock()):
        await grpc_async.async_start_notify()
        await asyncio.wait_for(grpc_async._notify_task, timeout=2.0)

    reconnect_cb.assert_awaited_once()
    assert any(u.path == "main.power" for u in updates)


async def test_disconnect_stops_connection_manager(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    """Intentional shutdown should not keep retrying reconnect."""

    def fake_start_notify(
        on_delta: Callable[[str, Any], None],
        on_connection_lost: Callable[[], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        del on_delta, on_connection_lost, on_reconnect

    grpc_async._client.start_notify = fake_start_notify  # type: ignore[method-assign]
    grpc_async._client.stop_notify = MagicMock()
    grpc_async._client.close = MagicMock()

    with patch.object(grpc_async, "_async_wait", new=AsyncMock()):
        await grpc_async.async_start_notify()
        await grpc_async.async_disconnect()

    assert grpc_async._notify_task is None
    assert not grpc_async.is_connected
