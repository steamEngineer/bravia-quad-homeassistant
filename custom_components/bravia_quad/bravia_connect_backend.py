"""HA sync façade over pybravia-connect (sticky notify cache stays in Theatre)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pybravia_connect import AuthError, BraviaConnectClient
from pybravia_connect import CapabilityMeta as LibCapabilityMeta
from pybravia_connect import ConnectionError as BraviaConnectionError

from .grpc.get_capabilities_response import (
    CapabilityMeta,
    int_range_from_capability,
    is_int_capability,
)

DeltaCallback = Callable[[str, Any], None]


def _to_ha_capability_index(
    index: dict[str, LibCapabilityMeta],
) -> dict[str, CapabilityMeta]:
    """Copy library CapabilityMeta into the Theatre dataclass (same fields)."""
    return {
        path: CapabilityMeta(
            name=meta.name,
            type=meta.type,
            min=meta.min,
            max=meta.max,
            values=meta.values,
        )
        for path, meta in index.items()
    }


class BraviaConnectBackend:
    """Sync wire client + HA sticky notify_state for BraviaGrpcClientAsync."""

    def __init__(self) -> None:
        """Initialize empty backend (call connect before RPCs)."""
        self._lib: BraviaConnectClient | None = None
        self._notify_state: dict[str, Any] = {}
        self._capability_paths: frozenset[str] | None = None
        self._capability_index: dict[str, CapabilityMeta] | None = None
        self.last_rpc_error: str | None = None
        self.last_error_is_transport: bool = False

    @property
    def notify_state(self) -> dict[str, Any]:
        """Latest values from StartNotifyStates / GetStates seed (path → value)."""
        return dict(self._notify_state)

    @property
    def capability_paths(self) -> frozenset[str] | None:
        """Device-advertised path names from GetCapabilities, if fetched."""
        return self._capability_paths

    @property
    def capability_index(self) -> dict[str, CapabilityMeta] | None:
        """Per-path GetCapabilities metadata (type/min/max), if fetched."""
        return self._capability_index

    def is_int_capability(self, path: str) -> bool | None:
        """Return whether *path* is capability type int; None if unknown."""
        return is_int_capability(path, self._capability_index)

    def int_range(self, path: str) -> tuple[int, int] | None:
        """Return capability min/max for an int path when both are present."""
        return int_range_from_capability(path, self._capability_index)

    def connect(self, host: str, port: int, *, keys: dict[str, str | None]) -> None:
        """
        Build a library client and run the auth handshake.

        *keys* must include ``device_id`` and ``hmac_key``; ``key_id`` /
        ``session_key`` are optional.
        """
        device_id = keys.get("device_id")
        hmac_key = keys.get("hmac_key")
        if not device_id or not hmac_key:
            msg = "device_id and hmac_key required"
            raise BraviaConnectionError(msg)
        self.close()
        self.last_rpc_error = None
        self.last_error_is_transport = False
        self._lib = BraviaConnectClient(
            host,
            port,
            device_id=device_id,
            hmac_key=hmac_key,
            key_id=keys.get("key_id"),
            session_key=keys.get("session_key"),
        )
        try:
            self._lib.connect()
        except BraviaConnectionError as err:
            self.last_rpc_error = str(err)
            self.last_error_is_transport = True
            self._lib = None
            raise
        except AuthError as err:
            self.last_rpc_error = str(err)
            self.last_error_is_transport = False
            self._lib = None
            raise

    def close(self) -> None:
        """Stop notify and close the library channel."""
        if self._lib is not None:
            self._lib.close()
            self._lib = None

    # Alias used by older async disconnect paths / tests.
    disconnect = close

    def fetch_capabilities(self) -> frozenset[str] | None:
        """Fetch GetCapabilities; soft-fail to None on error."""
        if self._lib is None:
            return None
        try:
            index = self._lib.get_capabilities()
        except (BraviaConnectionError, AuthError, OSError) as err:
            self.last_rpc_error = str(err)
            return None
        ha_index = _to_ha_capability_index(index)
        self._capability_index = ha_index
        self._capability_paths = frozenset(ha_index)
        return self._capability_paths

    def get_states(self, paths: list[str] | None = None) -> dict[str, Any] | None:
        """Signed GetStates; None on failure."""
        if self._lib is None:
            return None
        try:
            return self._lib.get_states(paths)
        except (BraviaConnectionError, AuthError, OSError, ValueError) as err:
            self.last_rpc_error = str(err)
            return None

    def get_states_dict(self, *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        """Compatibility wrapper: bulk GetStates via library safe paths."""
        return self.get_states()

    def get_states_with_preflight(
        self, *_args: Any, **_kwargs: Any
    ) -> dict[str, Any] | None:
        """Compatibility wrapper: library get_states (session-locked internally)."""
        return self.get_states()

    def get_states_app_sequence(
        self, *_args: Any, **_kwargs: Any
    ) -> dict[str, Any] | None:
        """Compatibility wrapper: bulk GetStates for seed / config-flow paths."""
        return self.get_states()

    def get_states_single_path(
        self,
        field_path: str,
        *,
        use_signed_auth: bool = False,
        quiet: bool = False,
    ) -> dict[str, Any] | None:
        """Signed single-path GetStates."""
        del use_signed_auth, quiet
        snapshot = self.get_states([field_path])
        if not snapshot:
            return None
        return snapshot

    def exec_command(
        self,
        command_path: str,
        value: Any = None,
        string_value: str | None = None,
        *,
        int_value: int | None = None,
        bool_value: bool | None = None,
    ) -> bool:
        """Coalesce HA kwargs into a single value for the library client."""
        if self._lib is None:
            return False
        if bool_value is not None:
            payload: Any = bool_value
        elif int_value is not None:
            payload = int_value
        elif string_value is not None:
            payload = string_value
        else:
            payload = value
        if payload is None:
            return False
        try:
            return self._lib.exec_command(command_path, payload)
        except (BraviaConnectionError, AuthError, OSError) as err:
            self.last_rpc_error = str(err)
            return False

    def start_notify(
        self,
        on_delta: DeltaCallback,
        on_connection_lost: Callable[[], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        """Start library notify; sticky-merge each delta into HA notify_state."""
        if self._lib is None:
            msg = "not connected"
            raise BraviaConnectionError(msg)

        def _wrapped(path: str, value: Any) -> None:
            self.update_notify_cache({path: value})
            on_delta(path, value)

        self._lib.start_notify(
            _wrapped,
            on_connection_lost=on_connection_lost,
            on_reconnect=on_reconnect,
        )

    def stop_notify(self) -> None:
        """Stop the library notify worker."""
        if self._lib is not None:
            self._lib.stop_notify()

    @staticmethod
    def _is_clearing_unavailable_reason(value: Any) -> bool:
        if value is None:
            return True
        return str(value).lower() in ("", "none")

    def _should_retain_unavailable_reason(
        self, path: str, new_value: Any, pending: dict[str, Any]
    ) -> bool:
        if not path.endswith(".unavailable_reason"):
            return False
        if not self._is_clearing_unavailable_reason(new_value):
            return False
        old = self._notify_state.get(path)
        if old is None or self._is_clearing_unavailable_reason(old):
            return False
        base = path[: -len(".unavailable_reason")]
        avail_path = f"{base}.availability"
        availability = pending.get(avail_path, self._notify_state.get(avail_path))
        return availability is not True

    def export_feature_unavailable_reasons(self) -> dict[str, str]:
        """Return ``*.unavailable_reason`` paths that currently block a feature."""
        out: dict[str, str] = {}
        for path, value in self._notify_state.items():
            if not path.endswith(".unavailable_reason"):
                continue
            if value is None or self._is_clearing_unavailable_reason(value):
                continue
            out[path] = str(value)
        return out

    def apply_persisted_feature_unavailable_reasons(
        self, persisted: dict[str, Any] | None
    ) -> int:
        """Re-apply last-known real reasons after GetStates seed."""
        if not persisted:
            return 0
        applied = 0
        for path, reason in persisted.items():
            if not isinstance(path, str) or not path.endswith(".unavailable_reason"):
                continue
            if reason is None or self._is_clearing_unavailable_reason(reason):
                continue
            current = self._notify_state.get(path)
            if current is not None and not self._is_clearing_unavailable_reason(
                current
            ):
                continue
            base = path[: -len(".unavailable_reason")]
            avail_path = f"{base}.availability"
            self._notify_state[path] = str(reason)
            self._notify_state.pop(avail_path, None)
            applied += 1
        return applied

    def update_notify_cache(self, updates: dict[str, Any]) -> None:
        """Merge path values into the notify cache (sticky unavailable_reason)."""
        if not updates:
            return
        pending = dict(updates)
        if len(pending) > 1:
            for path, value in list(pending.items()):
                if not path.endswith(".unavailable_reason"):
                    continue
                if not self._is_clearing_unavailable_reason(value):
                    continue
                avail_path = f"{path[: -len('.unavailable_reason')]}.availability"
                if pending.get(avail_path) is True:
                    pending[avail_path] = None
        filtered = {
            path: value
            for path, value in pending.items()
            if not self._should_retain_unavailable_reason(path, value, pending)
        }
        if filtered:
            self._notify_state.update(filtered)

    def session_auth_snapshot(self) -> dict[str, Any]:
        """HA-side debug fields (library has no session_auth_snapshot)."""
        return {
            "connected": self._lib is not None,
            "last_rpc_error": self.last_rpc_error,
        }
