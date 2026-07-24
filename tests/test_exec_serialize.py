"""Regression test: session-authenticated ExecCommand must be serialized.

Concurrent ExecCommand writes each do a fresh GetSessionRandom on the shared
session; if they run concurrently the device firmware crashes (see the exec
serialization issue). async_exec_command must therefore never run two `_run`
bodies at once.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync


@pytest.mark.asyncio
async def test_async_exec_command_is_serialized() -> None:
    client = BraviaGrpcClientAsync(
        "192.0.2.10",  # TEST-NET-1; no real device
        device_id="dev",
        key_id="kid",
        session_key="s" * 64,
        hmac_key="h" * 64,
    )
    client._connected = True

    running = 0
    max_running = 0
    counter_lock = threading.Lock()
    release = threading.Event()

    def fake_exec(*_args: object, **_kwargs: object) -> bool:
        # Runs in a worker thread via asyncio.to_thread.
        nonlocal running, max_running
        with counter_lock:
            running += 1
            max_running = max(max_running, running)
        # Hold so an unserialized second call would overlap here.
        release.wait(timeout=2.0)
        with counter_lock:
            running -= 1
        return True

    client._client.exec_command = fake_exec  # type: ignore[method-assign]

    first = asyncio.create_task(client.async_exec_command("a", bool_value=True))
    await asyncio.sleep(0.1)  # let `first` enter fake_exec and hold
    second = asyncio.create_task(client.async_exec_command("b", bool_value=True))
    await asyncio.sleep(0.1)  # `second` must block on the lock, not enter fake_exec
    release.set()

    assert await first is True
    assert await second is True
    assert max_running == 1  # never overlapped -> serialized
