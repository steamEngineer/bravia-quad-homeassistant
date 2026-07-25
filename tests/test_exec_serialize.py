"""Regression test: session-authenticated RPCs must be serialized.

Concurrent ExecCommand writes each do a fresh GetSessionRandom on the shared
session; if they run concurrently the device firmware crashes (see the exec
serialization issue). Supplemental GetStates (backfill / fetch_field_paths)
mutates the same session tokens, so those wire calls must not overlap exec
either. async_exec_command and GetStates helpers must therefore never run two
session wire bodies at once.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync


def _connected_client() -> BraviaGrpcClientAsync:
    client = BraviaGrpcClientAsync(
        "192.0.2.10",  # TEST-NET-1; no real device
        device_id="dev",
        key_id="kid",
        session_key="s" * 64,
        hmac_key="h" * 64,
    )
    client._connected = True
    return client


@pytest.mark.asyncio
async def test_async_exec_command_is_serialized() -> None:
    client = _connected_client()

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


@pytest.mark.asyncio
async def test_exec_and_fetch_field_paths_are_serialized() -> None:
    """Exec must not overlap supplemental GetStates (media-player backfill path)."""
    client = _connected_client()

    running = 0
    max_running = 0
    counter_lock = threading.Lock()
    release = threading.Event()

    def fake_exec(*_args: object, **_kwargs: object) -> bool:
        nonlocal running, max_running
        with counter_lock:
            running += 1
            max_running = max(max_running, running)
        release.wait(timeout=2.0)
        with counter_lock:
            running -= 1
        return True

    def fake_get_states_single_path(
        path: str,
        *,
        use_signed_auth: bool = False,
        quiet: bool = False,
    ) -> dict[str, object]:
        del use_signed_auth, quiet
        nonlocal running, max_running
        with counter_lock:
            running += 1
            max_running = max(max_running, running)
        release.wait(timeout=2.0)
        with counter_lock:
            running -= 1
        return {path: True}

    client._client.exec_command = fake_exec  # type: ignore[method-assign]
    client._client.get_states_single_path = (  # type: ignore[method-assign]
        fake_get_states_single_path
    )

    exec_task = asyncio.create_task(client.async_exec_command("a", bool_value=True))
    await asyncio.sleep(0.1)  # let exec enter fake_exec and hold
    fetch_task = asyncio.create_task(client.async_fetch_field_paths(["playback.power"]))
    await asyncio.sleep(0.1)  # fetch must block on the lock, not enter GetStates
    release.set()

    assert await exec_task is True
    assert await fetch_task == 1
    assert max_running == 1
