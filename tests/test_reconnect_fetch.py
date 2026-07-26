"""Test adapter reconnect hooks and disconnected send semantics."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock

import pytest

from custom_components.bravia_quad.bravia_quad_client import BraviaQuadClient


@pytest.fixture
def client() -> BraviaQuadClient:
    """Return a client instance."""
    return BraviaQuadClient("127.0.0.1", "Test")


async def _cancel_background(client: BraviaQuadClient) -> None:
    """Cancel and await adapter background tasks."""
    for task in list(client._background_tasks):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    client._background_tasks.clear()


async def test_send_command_raises_when_disconnected(
    client: BraviaQuadClient,
) -> None:
    """Commands fail immediately when not connected."""
    assert not client.is_connected
    with pytest.raises(ConnectionError):
        await client.async_send_command({"type": "get", "feature": "main.power"})


async def test_fetch_is_not_awaited_during_reconnect(
    client: BraviaQuadClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """State fetch after reconnect must not block the reconnect path.

    If awaited inline, the fetch deadlocks: it sends commands that
    need the read loop, but the read loop can't run until the
    reconnect path returns.
    """
    fetch_event = asyncio.Event()

    async def slow_fetch() -> None:
        fetch_event.set()
        await asyncio.sleep(999)

    monkeypatch.setattr(client, "async_fetch_all_states", slow_fetch)

    # If _async_on_lib_reconnect awaits slow_fetch, it blocks for 999s.
    # If it schedules the fetch without awaiting, it returns promptly.
    try:
        await asyncio.wait_for(client._async_on_lib_reconnect(), timeout=1.0)
    except TimeoutError:
        pytest.fail(
            "_async_on_lib_reconnect did not return within 1s, "
            "likely awaiting async_fetch_all_states inline"
        )

    try:
        await asyncio.wait_for(fetch_event.wait(), timeout=1.0)
    except TimeoutError:
        pytest.fail("async_fetch_all_states was never called")

    assert client.is_connected
    await _cancel_background(client)


async def test_notify_wrap_updates_sticky_and_callbacks(
    client: BraviaQuadClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Library notify bridge updates sticky cache and entity callbacks."""
    monkeypatch.setattr(client, "async_get_input", AsyncMock())
    seen: list[str] = []

    def _on_power(value: object) -> None:
        seen.append(str(value))

    client.register_notification_callback("main.power", _on_power)
    await client._on_lib_notify("main.power", "on")

    assert client.power_state == "on"
    assert seen == ["on"]
    await _cancel_background(client)


async def test_send_command_set_facade(client: BraviaQuadClient) -> None:
    """async_send_command maps set dicts onto library set_feature."""
    client._connected = True
    client._lib.set_feature = AsyncMock(return_value="ACK")

    response = await client.async_send_command(
        {"type": "set", "feature": "bluetooth.mode", "value": "RX"}
    )

    assert response == {
        "type": "result",
        "feature": "bluetooth.mode",
        "value": "ACK",
    }
    client._lib.set_feature.assert_awaited_once_with("bluetooth.mode", "RX")
