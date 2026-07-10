"""Async Home Assistant wrapper for the Bravia gRPC client."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import logging
import socket
import time
from typing import TYPE_CHECKING, Any

from .const import DEFAULT_GRPC_PORT, RECONNECT_INITIAL_DELAY, RECONNECT_MAX_DELAY
from .external_control import async_ensure_external_control_enabled
from .grpc.client import BraviaGrpcClient, NotifyStateUpdate, load_keys_from_file
from .grpc_mapping import (
    NOTIFY_ONLY_GRPC_PATHS,
    entity_critical_grpc_paths,
    missing_entity_paths,
)
from .grpc_seeds_seed import SEEDS_SEED_PATHS, async_seed_from_seeds
from .grpc_tcp_seed import async_seed_notify_only_from_tcp

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from homeassistant.core import HomeAssistant

    ReconnectCallback = Callable[[], Awaitable[None]]
    RefreshKeysCallback = Callable[[], Awaitable[bool]]

_LOGGER = logging.getLogger(__name__)
_DOMAIN_LOGGER = logging.getLogger("custom_components.bravia_quad")


def _session_lost_reason(last_rpc_error: str | None) -> str:
    """Human-readable reason when the notify stream drops."""
    if not last_rpc_error:
        return "notify stream ended (BRAVIA Connect may have taken over)"
    lowered = last_rpc_error.lower()
    if "too many ping" in lowered:
        return last_rpc_error
    if "unavailable" in lowered and not any(
        token in lowered
        for token in ("connection refused", "failed to connect", "settings timeout")
    ):
        return f"{last_rpc_error} (BRAVIA Connect may have taken over)"
    return last_rpc_error


class BraviaGrpcClientAsync:
    """Asyncio facade over the sync gRPC client (runs blocking calls in executor)."""

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_GRPC_PORT,
        device_id: str | None = None,
        key_id: str | None = None,
        session_key: str | None = None,
        hmac_key: str | None = None,
        debug: bool = False,
        session_keys_expires_at: int | None = None,
        seeds_poll: bool = False,
        credentials: dict[str, Any] | None = None,
        hass: HomeAssistant | None = None,
    ) -> None:
        """Initialize async gRPC client wrapper."""
        self.host = host
        self.port = port
        self.device_id = device_id
        self.key_id = key_id
        self.session_key = session_key
        self.hmac_key = hmac_key
        self.debug = debug
        self.session_keys_expires_at = session_keys_expires_at
        self.seeds_poll = seeds_poll
        self._credentials = dict(credentials or {})
        self._hass = hass
        self._client = BraviaGrpcClient(host, port, debug=debug)
        self._connected = False
        self._transport_error = False
        self._last_notify_at: float | None = None
        self._notify_task: asyncio.Task[None] | None = None
        self._notify_stop = asyncio.Event()
        self._state_callbacks: list[Callable[[NotifyStateUpdate], None]] = []
        self._reconnect_callback: ReconnectCallback | None = None
        self._refresh_keys_callback: RefreshKeysCallback | None = None
        self._availability_callbacks: set[Callable[[bool], None]] = set()
        self.volume_step_interval: int = 0

    @classmethod
    def from_keys_dict(
        cls, host: str, keys: dict[str, Any], **kwargs: Any
    ) -> BraviaGrpcClientAsync:
        """Build client from Sony Seeds keys JSON fields."""
        return cls(
            host,
            device_id=keys.get("device_id"),
            key_id=keys.get("key_id"),
            session_key=keys.get("session_key"),
            hmac_key=keys.get("hmac_key"),
            session_keys_expires_at=keys.get("session_keys_expires_at"),
            **kwargs,
        )

    @classmethod
    def from_keys_json(
        cls, host: str, keys_json: str, **kwargs: Any
    ) -> BraviaGrpcClientAsync:
        """Parse keys JSON string (config entry options)."""
        data = json.loads(keys_json)
        if not isinstance(data, dict):
            msg = "gRPC keys JSON must be an object"
            raise TypeError(msg)
        return cls.from_keys_dict(host, data, **kwargs)

    @staticmethod
    def parse_keys_file(path: str) -> dict[str, str]:
        """Load keys from JSON file (scripts/get_session_keys.py output)."""
        return load_keys_from_file(path)

    def add_state_callback(self, callback: Callable[[NotifyStateUpdate], None]) -> None:
        """Register callback for StartNotifyStates push updates."""
        self._state_callbacks.append(callback)

    def remove_state_callback(
        self, callback: Callable[[NotifyStateUpdate], None]
    ) -> None:
        """Unregister a StartNotifyStates push callback."""
        with contextlib.suppress(ValueError):
            self._state_callbacks.remove(callback)

    def set_reconnect_callback(self, callback: ReconnectCallback) -> None:
        """Run after a successful gRPC reconnect (e.g. refresh HA entity state)."""
        self._reconnect_callback = callback

    def set_refresh_keys_callback(self, callback: RefreshKeysCallback) -> None:
        """Run when authentication fails to refresh Sony Seeds session keys."""
        self._refresh_keys_callback = callback

    async def async_refresh_credentials(self) -> bool:
        """Refresh OAuth access token and gRPC session keys via the HA callback."""
        if self._refresh_keys_callback is None:
            return False
        return await self._refresh_keys_callback()

    def register_availability_callback(self, callback: Callable[[bool], None]) -> None:
        """Register a callback for gRPC session availability changes."""
        self._availability_callbacks.add(callback)

    def unregister_availability_callback(
        self, callback: Callable[[bool], None]
    ) -> None:
        """Unregister a gRPC session availability callback."""
        self._availability_callbacks.discard(callback)

    def _notify_availability(self, *, available: bool) -> None:
        """Notify entities when the gRPC session connects or drops."""
        for callback in tuple(self._availability_callbacks):
            try:
                callback(available)
            except Exception:
                _LOGGER.exception("Error in gRPC availability callback")

    def _set_connected(self, *, connected: bool) -> None:
        """Update connection flag and notify entities when availability changes."""
        if self._connected == connected:
            return
        self._connected = connected
        self._notify_availability(available=connected)

    def update_keys(self, keys: dict[str, Any]) -> None:
        """Replace Sony Seeds session key fields after OAuth refresh."""
        self.device_id = keys.get("device_id")
        self.key_id = keys.get("key_id")
        self.session_key = keys.get("session_key")
        self.hmac_key = keys.get("hmac_key")
        if keys.get("access_token"):
            self._credentials.update(keys)
        expires_at = keys.get("session_keys_expires_at")
        if expires_at is not None:
            self.session_keys_expires_at = int(expires_at)

    def _exec_failure_context(self, command_path: str) -> dict[str, Any]:
        """Session auth snapshot plus HA-side idle metadata for exec failures."""
        context = self._client.session_auth_snapshot()
        context["command_path"] = command_path
        context["key_id"] = self.key_id
        context["connected"] = self._connected
        if self.session_keys_expires_at is not None:
            context["session_keys_expires_at"] = self.session_keys_expires_at
            context["session_keys_expires_in_s"] = self.session_keys_expires_at - int(
                time.time()
            )
        if self._last_notify_at is not None:
            context["seconds_since_last_notify"] = round(
                time.monotonic() - self._last_notify_at, 1
            )
        return context

    def _trace_enabled(self) -> bool:
        """Integration option or HA logger DEBUG for bravia_quad."""
        return (
            self.debug
            or _LOGGER.isEnabledFor(logging.DEBUG)
            or _DOMAIN_LOGGER.isEnabledFor(logging.DEBUG)
        )

    def _debug(self, msg: str, *args: object) -> None:
        if not self._trace_enabled():
            return
        if self.debug:
            formatted = msg % args if args else msg
            _LOGGER.info("[gRPC debug] %s", formatted)
        else:
            _LOGGER.debug(msg, *args)

    @property
    def notify_state(self) -> dict[str, Any]:
        """Cached field-path values from the notify stream."""
        return self._client.notify_state

    @property
    def capability_paths(self) -> frozenset[str] | None:
        """Device-advertised path names from GetCapabilities, if fetched."""
        return self._client.capability_paths

    def merge_notify_cache(self, updates: dict[str, Any]) -> None:
        """Merge values into the underlying notify cache (GetStates/TCP seed)."""
        self._client.update_notify_cache(updates)

    @property
    def is_connected(self) -> bool:
        """Return whether gRPC is connected and authenticated."""
        return self._connected

    @property
    def is_transport_error(self) -> bool:
        """Return True when the last connect failed because gRPC is unreachable."""
        return self._transport_error

    @property
    def last_rpc_error(self) -> str | None:
        """Return the most recent gRPC RPC error string, if any."""
        return self._client.last_rpc_error

    @staticmethod
    def _grpc_port_connect_ex(host: str, port: int) -> int | str:
        """Return connect_ex for the gRPC port (0 = listening)."""
        sock = socket.socket()
        sock.settimeout(1.5)
        try:
            return sock.connect_ex((host, port))
        except OSError as exc:
            return f"err:{type(exc).__name__}"
        finally:
            sock.close()

    async def async_connect(self) -> bool:
        """Connect and authenticate with Sony Seeds session keys."""
        self._transport_error = False
        self._set_connected(connected=False)

        grpc_port_status = await asyncio.to_thread(
            self._grpc_port_connect_ex, self.host, self.port
        )
        if grpc_port_status == errno.ECONNREFUSED:
            self._transport_error = True
            _LOGGER.error(
                "gRPC port %s:%s connection refused (device not listening; "
                "HTTP/TCP may still be reachable)",
                self.host,
                self.port,
            )
            return False

        await asyncio.to_thread(self._client.connect)
        ok = await asyncio.to_thread(
            self._client.authenticate,
            session_key=self.session_key,
            hmac_key=self.hmac_key,
            key_id=self.key_id,
            device_id=self.device_id,
        )
        if ok:
            self._set_connected(connected=True)
            self._debug("Authenticated with %s:%s", self.host, self.port)
        elif self._client.last_error_is_transport:
            self._transport_error = True
            _LOGGER.error(
                "gRPC unavailable at %s:%s: %s",
                self.host,
                self.port,
                self._client.last_rpc_error or "transport error",
            )
        else:
            _LOGGER.error("gRPC authentication failed for %s:%s", self.host, self.port)
        return ok

    async def async_disconnect(self) -> None:
        """Stop notify task and close channel."""
        self._notify_stop.set()
        if self._notify_task and not self._notify_task.done():
            # Close channel first so the blocking notify iterator unblocks.
            await asyncio.to_thread(self._client.disconnect)
            self._notify_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._notify_task
            self._notify_task = None
        else:
            await asyncio.to_thread(self._client.disconnect)
        self._set_connected(connected=False)

    async def async_get_states(self) -> Any | None:
        """Fetch full device state snapshot."""
        if not self._connected:
            return None
        return await asyncio.to_thread(self._client.get_states)

    async def async_fetch_capabilities(self) -> frozenset[str] | None:
        """
        Fetch GetCapabilities and cache path names for GetStates filtering.

        Soft-fail: returns None on error; bulk GetStates keeps the full HA list.
        """
        return await asyncio.to_thread(self._client.fetch_capabilities)

    async def async_get_states_dict(self) -> dict[str, Any] | None:
        """Fetch GetStatesWithAuth as parsed field-path dict."""
        if not self._connected:
            return None
        snapshot = await asyncio.to_thread(
            self._client.get_states_with_preflight,
            use_signed_auth=True,
        )
        if snapshot:
            return snapshot
        return await asyncio.to_thread(
            self._client.get_states_dict,
            use_signed_auth=True,
        )

    async def async_get_states_app_sequence(self) -> dict[str, Any] | None:
        """Mirror BRAVIA Connect GetStates RPC order (signed full + mutex)."""
        if not self._connected:
            return None
        return await asyncio.to_thread(self._client.get_states_app_sequence)

    async def async_seed_notify_from_snapshot(self) -> int:
        """Merge GetStates snapshot into notify_state cache; return field count."""
        snapshot = await asyncio.to_thread(self._client.get_states_app_sequence)
        if not snapshot:
            snapshot = await self.async_get_states_dict()
        if not snapshot:
            _LOGGER.warning("gRPC GetStates snapshot failed for %s", self.host)
            return 0
        self._client.update_notify_cache(snapshot)
        self._debug(
            "GetStates snapshot seeded %d fields on %s", len(snapshot), self.host
        )
        return len(snapshot)

    async def async_backfill_entity_paths(self) -> tuple[int, int, int]:
        """
        Supplemental single-path GetStates for entity paths still unset after bulk seed.

        Returns ``(bulk_resolved, notify_only_resolved, still_missing_count)``.
        """
        if not self._connected:
            return 0, 0, len(entity_critical_grpc_paths())

        notify_only_set = set(NOTIFY_ONLY_GRPC_PATHS)
        bulk_resolved = 0

        for path in sorted(entity_critical_grpc_paths()):
            if path in notify_only_set:
                continue
            if self._client.notify_state.get(path) is not None:
                continue
            result = await asyncio.to_thread(
                self._client.get_states_single_path,
                path,
                use_signed_auth=True,
                quiet=True,
            )
            if result and result.get(path) is not None:
                self._client.update_notify_cache(result)
                bulk_resolved += 1

        notify_only_resolved = 0
        if (
            self.seeds_poll
            and self._hass is not None
            and self._credentials.get("access_token")
        ):
            notify_only_resolved = await async_seed_from_seeds(
                self._hass,
                self._credentials,
                self,
            )
        else:
            notify_only_resolved = await async_seed_notify_only_from_tcp(
                self.host, self
            )
        still_missing = len(missing_entity_paths(self._client.notify_state))
        if bulk_resolved or notify_only_resolved:
            total = len(entity_critical_grpc_paths())
            resolved = total - still_missing
            seed_source = "seeds-seed" if self.seeds_poll else "tcp-seed"
            _LOGGER.info(
                "gRPC entity path backfill on %s: %d/%d resolved "
                "(bulk single-path +%d, %s +%d, %d still missing)",
                self.host,
                resolved,
                total,
                bulk_resolved,
                seed_source,
                notify_only_resolved,
                still_missing,
            )
        elif still_missing:
            self._debug(
                "gRPC entity path backfill on %s: 0 resolved, %d still missing",
                self.host,
                still_missing,
            )
        return bulk_resolved, notify_only_resolved, still_missing

    def unresolved_entity_paths(self) -> frozenset[str]:
        """Entity paths still missing or ``None`` in notify_state."""
        return missing_entity_paths(self._client.notify_state)

    async def async_fetch_field_paths(self, paths: list[str]) -> int:
        """GetStates per path (skips notify-only paths the device rejects)."""
        if not self._connected or not paths:
            return 0
        notify_only = set(NOTIFY_ONLY_GRPC_PATHS)
        resolved = 0
        for path in paths:
            if path in notify_only:
                continue
            if self._client.notify_state.get(path) is not None:
                continue
            snapshot = await asyncio.to_thread(
                self._client.get_states_single_path,
                path,
                use_signed_auth=True,
                quiet=True,
            )
            if snapshot and snapshot.get(path) is not None:
                self._client.update_notify_cache(snapshot)
                resolved += 1
        if resolved:
            self._debug(
                "GetStates supplemental fetch resolved %d paths on %s",
                resolved,
                self.host,
            )
        return resolved

    async def async_warmup_notify(
        self,
        missing_paths: frozenset[str] | None = None,
        timeout: float = 3.0,
    ) -> frozenset[str]:
        """
        Wait for StartNotifyStates to deliver values for unresolved entity paths.

        Returns paths still missing after *timeout* (empty when all resolved).
        """
        waiting = set(
            missing_paths
            if missing_paths is not None
            else self.unresolved_entity_paths()
        )
        if timeout <= 0 or not waiting:
            return frozenset(waiting)

        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline and waiting:
            waiting -= {
                path
                for path in waiting
                if self._client.notify_state.get(path) is not None
            }
            if not waiting:
                break
            await asyncio.sleep(0.05)

        still_missing = frozenset(waiting)
        if still_missing:
            self._debug(
                "gRPC notify warmup on %s: %d entity paths still unset after %.1fs",
                self.host,
                len(still_missing),
                timeout,
            )
        else:
            self._debug(
                "gRPC notify warmup on %s: all entity paths resolved within %.1fs",
                self.host,
                timeout,
            )
        return still_missing

    async def async_exec_command(
        self,
        command_path: str,
        *,
        value: int | None = None,
        string_value: str | None = None,
        int_value: int | None = None,
        bool_value: bool | None = None,
    ) -> bool:
        """Execute ExecCommandWithAuth."""
        if not self._connected:
            return False

        def _run() -> bool:
            return self._client.exec_command(
                command_path,
                value,
                string_value,
                int_value=int_value,
                bool_value=bool_value,
            )

        self._debug(
            "ExecCommand %s value=%s string=%s int=%s bool=%s",
            command_path,
            value,
            string_value,
            int_value,
            bool_value,
        )
        ok = await asyncio.to_thread(_run)
        if ok:
            self._debug("ExecCommand %s -> True", command_path)
            if (
                self.seeds_poll
                and self._hass is not None
                and command_path in SEEDS_SEED_PATHS
            ):
                await async_seed_from_seeds(
                    self._hass,
                    self._credentials,
                    self,
                    paths=frozenset({command_path}),
                )
        else:
            context = self._exec_failure_context(command_path)
            _LOGGER.warning(
                "ExecCommand %s failed (session may be stale): %s",
                command_path,
                context,
            )
            if await self._async_restore_session():
                self._debug(
                    "ExecCommand %s retrying after session restore",
                    command_path,
                )
                ok = await asyncio.to_thread(_run)
                if ok:
                    self._debug("ExecCommand %s -> True after restore", command_path)
                else:
                    _LOGGER.warning(
                        "ExecCommand %s failed after session restore: %s",
                        command_path,
                        self._exec_failure_context(command_path),
                    )
        return ok

    async def async_exec_denormalized(
        self,
        command_path: str,
        kind: str,
        payload: bool | int | str | None,
    ) -> bool:
        """Execute ExecCommand using a denormalize_for_exec kind/payload pair."""
        if kind == "bool_value":
            if not isinstance(payload, bool):
                if payload is None:
                    return False
                bool_payload = bool(payload)
            else:
                bool_payload = payload
            return await self.async_exec_command(command_path, bool_value=bool_payload)
        if kind == "int_value":
            if payload is None:
                return False
            return await self.async_exec_command(command_path, int_value=int(payload))
        if kind == "string_value":
            if payload is None:
                return False
            return await self.async_exec_command(
                command_path, string_value=str(payload)
            )
        return False

    async def async_start_notify(self) -> None:
        """Start background connection manager (notify stream + auto-reconnect)."""
        if self._notify_task and not self._notify_task.done():
            return
        self._notify_stop.clear()
        self._notify_task = asyncio.create_task(self._connection_manager())

    async def async_stop_notify(self) -> None:
        """Stop notify background task."""
        self._notify_stop.set()
        if self._notify_task:
            self._notify_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._notify_task
            self._notify_task = None

    async def _connection_manager(self) -> None:
        """Keep StartNotifyStates alive; reconnect when the app or device drops HA."""
        delay = RECONNECT_INITIAL_DELAY
        try:
            while not self._notify_stop.is_set():
                if not self._connected:
                    self._debug("Restoring gRPC session to %s", self.host)
                    if await self._async_restore_session():
                        delay = RECONNECT_INITIAL_DELAY
                    else:
                        _LOGGER.warning(
                            "gRPC reconnect to %s failed; retry in %ds",
                            self.host,
                            delay,
                        )
                        await self._async_wait(delay)
                        delay = min(delay * 2, RECONNECT_MAX_DELAY)
                        continue

                await self._run_notify_stream()

                if self._notify_stop.is_set():
                    break

                self._set_connected(connected=False)
                await asyncio.to_thread(self._client.disconnect)
                self._debug(
                    "Notify stream ended on %s; reconnect scheduled in %ds",
                    self.host,
                    delay,
                )
                _LOGGER.warning(
                    "gRPC session lost on %s (%s); reconnect in %ds",
                    self.host,
                    _session_lost_reason(self.last_rpc_error),
                    delay,
                )
                await self._async_wait(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except asyncio.CancelledError:
            self._notify_stop.set()
            await asyncio.to_thread(self._client.disconnect)
            _LOGGER.debug("gRPC connection manager cancelled for %s", self.host)
            raise

    async def _async_wait(self, seconds: float) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._notify_stop.wait(), timeout=seconds)

    async def _async_restore_session(self) -> bool:
        """Reconnect, authenticate, snapshot seed, and refresh entity callbacks."""
        await asyncio.to_thread(self._client.disconnect)
        if not await self.async_connect():
            # Connection refused / unreachable is not a credentials problem.
            if self.is_transport_error:
                return False
            if self._refresh_keys_callback is not None:
                refreshed = await self._refresh_keys_callback()
                if refreshed and await self.async_connect():
                    pass
                else:
                    return False
            else:
                return False

        await self.async_fetch_capabilities()

        await async_ensure_external_control_enabled(self.host, grpc_client=self)

        seeded = await self.async_seed_notify_from_snapshot()
        if seeded:
            _LOGGER.info(
                "gRPC reconnected to %s; seeded %d fields",
                self.host,
                seeded,
            )
        else:
            _LOGGER.warning(
                "gRPC reconnected to %s but GetStates seed failed", self.host
            )
        await self.async_backfill_entity_paths()
        self._dispatch_snapshot_callbacks()
        if self._reconnect_callback is not None:
            try:
                await self._reconnect_callback()
            except Exception:
                _LOGGER.exception("gRPC reconnect callback failed")
        return True

    def _dispatch_snapshot_callbacks(self) -> None:
        """Push cached notify_state to registered callbacks (post-reconnect refresh)."""
        for path, value in self._client.notify_state.items():
            if value is None:
                continue
            update = NotifyStateUpdate(path=path, value=value)
            for callback in self._state_callbacks:
                try:
                    callback(update)
                except Exception:
                    _LOGGER.exception("gRPC snapshot callback failed for %s", path)

    def dispatch_snapshot_callbacks(self) -> None:
        """Public entry: refresh entities from cached notify_state."""
        self._dispatch_snapshot_callbacks()

    async def _run_notify_stream(self) -> None:
        """Bridge blocking gRPC stream to async callbacks until the stream ends."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[NotifyStateUpdate | None] = asyncio.Queue()

        def _stream_worker() -> None:
            try:
                for states in self._client.start_notify_states():
                    if self._notify_stop.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, states)
            except Exception:
                _LOGGER.exception("gRPC notify stream failed")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = loop.run_in_executor(None, _stream_worker)
        try:
            while not self._notify_stop.is_set():
                states = await queue.get()
                if states is None:
                    break
                self._last_notify_at = time.monotonic()
                self._debug("Notify delta %s=%r", states.path, states.value)
                for callback in self._state_callbacks:
                    try:
                        callback(states)
                    except Exception:
                        _LOGGER.exception("gRPC state callback failed")
        finally:
            await asyncio.to_thread(self._client.disconnect)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(worker, timeout=3.0)

    async def async_iter_notifications(self) -> AsyncIterator[NotifyStateUpdate]:
        """Async iterator over state notifications (for scripts/tests)."""
        if not self._connected:
            return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[NotifyStateUpdate | None] = asyncio.Queue()

        def _stream_worker() -> None:
            try:
                for states in self._client.start_notify_states():
                    loop.call_soon_threadsafe(queue.put_nowait, states)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = loop.run_in_executor(None, _stream_worker)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await worker
