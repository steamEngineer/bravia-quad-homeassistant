"""Test connection lifecycle and TCP stream handling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.bravia_quad.bravia_quad_client import BraviaQuadClient


@pytest.fixture
def client() -> BraviaQuadClient:
    """Return a client instance."""
    return BraviaQuadClient("127.0.0.1", "Test")


def _make_writer() -> MagicMock:
    """Create a mock writer."""
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


async def test_notification_loop_exits_on_eof(
    client: BraviaQuadClient,
) -> None:
    """The read loop exits on EOF instead of reconnecting inline."""
    client._connected = True
    client._reader = AsyncMock()
    client._reader.read = AsyncMock(return_value=b"")
    client._writer = _make_writer()

    try:
        await asyncio.wait_for(client._notification_loop(), timeout=2.0)
    except TimeoutError:
        pytest.fail("Notification loop did not exit on EOF")

    assert not client._connected


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
    client._listening = True

    async def fake_connect() -> None:
        client._connected = True

    fetch_event = asyncio.Event()

    async def slow_fetch() -> None:
        fetch_event.set()
        await asyncio.sleep(999)

    real_sleep = asyncio.sleep

    async def short_sleep(delay: float) -> None:
        """Skip reconnect delays but let slow_fetch actually block."""
        if delay < 60:
            return
        await real_sleep(delay)

    monkeypatch.setattr(client, "async_connect", fake_connect)
    monkeypatch.setattr(client, "async_fetch_all_states", slow_fetch)
    monkeypatch.setattr(asyncio, "sleep", short_sleep)

    task = asyncio.create_task(client._reconnect_loop())

    # If _reconnect_loop awaits slow_fetch, it blocks for 999s.
    # If it schedules the fetch without awaiting, it returns promptly.
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except TimeoutError:
        pytest.fail(
            "_reconnect_loop did not return within 1s, "
            "likely awaiting async_fetch_all_states inline"
        )

    # The fetch should have been triggered
    assert fetch_event.is_set(), "async_fetch_all_states was never called"

    for t in list(client._background_tasks):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


async def test_split_message_not_lost(
    client: BraviaQuadClient,
) -> None:
    """A JSON object split across two TCP reads is still processed."""
    msg = '{"feature":"hdmi.passthrough","id":1,"type":"result","value":"auto"}'
    split_at = 30
    chunk1 = msg[:split_at].encode()
    chunk2 = msg[split_at:].encode()

    reads = iter([chunk1, chunk2, b""])
    reader = AsyncMock()
    reader.read = AsyncMock(side_effect=lambda n: next(reads))

    client._connected = True
    client._reader = reader
    client._writer = _make_writer()

    processed: list[dict] = []
    original = client._process_incoming_message

    async def capture(message: dict) -> None:
        processed.append(message)
        await original(message)

    client._process_incoming_message = capture

    await client._notification_loop()

    assert len(processed) == 1
    assert processed[0]["feature"] == "hdmi.passthrough"
    assert processed[0]["value"] == "auto"


async def test_burst_split_across_reads_no_messages_lost(
    client: BraviaQuadClient,
) -> None:
    """A burst of messages split at arbitrary byte boundaries loses nothing."""
    import json as json_mod

    messages = [
        json_mod.dumps({"feature": f"test.{i}", "type": "notify", "value": str(i)})
        for i in range(20)
    ]
    full_stream = "".join(messages)

    chunk_size = 80
    chunks = [
        full_stream[i : i + chunk_size].encode()
        for i in range(0, len(full_stream), chunk_size)
    ]
    chunks.append(b"")

    reads = iter(chunks)
    reader = AsyncMock()
    reader.read = AsyncMock(side_effect=lambda n: next(reads))

    client._connected = True
    client._reader = reader
    client._writer = _make_writer()

    processed: list[dict] = []

    async def capture(message: dict) -> None:
        processed.append(message)

    client._process_incoming_message = capture

    await client._notification_loop()

    assert len(processed) == 20
    features = {m["feature"] for m in processed}
    for i in range(20):
        assert f"test.{i}" in features
