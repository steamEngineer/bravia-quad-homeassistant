"""Tests for BraviaGrpcClientAsync exec failure recovery."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync


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
    client._client.exec_command = MagicMock()
    return client


@pytest.mark.asyncio
async def test_async_exec_command_retries_after_session_restore(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    grpc_async._client.exec_command.side_effect = [False, True]

    with patch.object(
        grpc_async, "_async_restore_session", new=AsyncMock(return_value=True)
    ) as restore:
        ok = await grpc_async.async_exec_command("power", bool_value=True)

    assert ok is True
    assert grpc_async._client.exec_command.call_count == 2
    restore.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_exec_command_no_retry_when_restore_fails(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    grpc_async._client.exec_command.return_value = False

    with patch.object(
        grpc_async, "_async_restore_session", new=AsyncMock(return_value=False)
    ):
        ok = await grpc_async.async_exec_command("power", bool_value=True)

    assert ok is False
    grpc_async._client.exec_command.assert_called_once()


@pytest.mark.asyncio
async def test_async_exec_command_skips_restore_on_success(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    grpc_async._client.exec_command.return_value = True

    with patch.object(grpc_async, "_async_restore_session", new=AsyncMock()) as restore:
        ok = await grpc_async.async_exec_command("volume", int_value=10)

    assert ok is True
    restore.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_exec_command_skips_restore_when_session_alive(
    grpc_async: BraviaGrpcClientAsync,
) -> None:
    """Empty power response during transition must not tear down a live notify."""
    grpc_async._client.exec_command.return_value = False
    grpc_async._last_notify_at = time.monotonic()

    with patch.object(grpc_async, "_async_restore_session", new=AsyncMock()) as restore:
        ok = await grpc_async.async_exec_command("power", bool_value=True)

    assert ok is False
    grpc_async._client.exec_command.assert_called_once()
    restore.assert_not_awaited()
