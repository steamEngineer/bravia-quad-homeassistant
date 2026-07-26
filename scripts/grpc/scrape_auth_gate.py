"""OAuth refresh + gRPC handshake gate for device capability scrape."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pybravia_connect import (
    DEFAULT_THEATRE_PORT,
    AuthError,
    BraviaConnectClient,
    refresh_credentials,
    write_credentials,
)
from pybravia_connect import ConnectionError as BraviaConnectionError

DEFAULT_KEYS_PATH = Path(__file__).resolve().parent / "session_keys.json"


@dataclass
class AuthGateReport:
    """Result of credential refresh and gRPC handshake gate."""

    refresh_ok: bool
    auth_ok: bool
    session_keys_expires_at: int | None = None
    confirm_signin: bool = False
    get_nonce: bool = False
    get_session_random: bool = False
    notify_stream_ok: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "refresh_ok": self.refresh_ok,
            "auth_ok": self.auth_ok,
            "session_keys_expires_at": self.session_keys_expires_at,
            "confirm_signin": self.confirm_signin,
            "get_nonce": self.get_nonce,
            "get_session_random": self.get_session_random,
            "notify_stream_ok": self.notify_stream_ok,
            "error": self.error,
        }


def refresh_keys_file(keys_path: Path) -> dict[str, Any]:
    """Refresh Sony Seeds credentials and write back to *keys_path*."""
    credentials = json.loads(keys_path.read_text(encoding="utf-8"))
    refreshed = refresh_credentials(credentials)
    write_credentials(keys_path, refreshed)
    return refreshed


def _connect_client(host: str, keys: dict[str, Any]) -> BraviaConnectClient:
    device_id = keys.get("device_id")
    hmac_key = keys.get("hmac_key")
    if not device_id or not hmac_key:
        msg = "keys missing device_id or hmac_key"
        raise ValueError(msg)
    client = BraviaConnectClient(
        host,
        DEFAULT_THEATRE_PORT,
        device_id=device_id,
        hmac_key=hmac_key,
        key_id=keys.get("key_id"),
        session_key=keys.get("session_key"),
    )
    client.connect()
    return client


def run_auth_gate(
    host: str,
    keys: dict[str, Any],
    *,
    debug: bool = False,
    check_notify: bool = False,
) -> AuthGateReport:
    """Connect and authenticate; optionally verify notify stream opens."""
    del debug  # library has no sync debug flag; kept for CLI compat
    report = AuthGateReport(
        refresh_ok=True,
        auth_ok=False,
        session_keys_expires_at=keys.get("session_keys_expires_at"),
    )
    client: BraviaConnectClient | None = None
    try:
        client = _connect_client(host, keys)
        report.auth_ok = True
        report.confirm_signin = True
        # connect() completes ConfirmSignin/ConfirmKeys/GetSessionRandom.
        report.get_nonce = True
        report.get_session_random = True
        if check_notify:
            notify_ok = False
            seen = threading.Event()

            def _on_delta(_path: str, _value: Any) -> None:
                nonlocal notify_ok
                notify_ok = True
                seen.set()

            client.start_notify(_on_delta)
            seen.wait(timeout=2.0)
            client.stop_notify()
            report.notify_stream_ok = notify_ok
    except (AuthError, BraviaConnectionError, OSError, ValueError) as exc:
        report.error = str(exc)
        report.auth_ok = False
    finally:
        if client is not None:
            client.close()
    return report


def gate_or_exit(
    host: str,
    keys_path: Path,
    *,
    refresh: bool = False,
    debug: bool = False,
    check_notify: bool = False,
) -> tuple[dict[str, Any], AuthGateReport]:
    """Refresh (optional), run gate; exit process on failure."""
    keys: dict[str, Any]
    report = AuthGateReport(refresh_ok=not refresh, auth_ok=False)
    if refresh:
        try:
            keys = refresh_keys_file(keys_path)
            report.refresh_ok = True
            report.session_keys_expires_at = keys.get("session_keys_expires_at")
        except (ValueError, OSError, RuntimeError) as exc:
            report.refresh_ok = False
            report.error = f"OAuth refresh failed: {exc}"
            print(json.dumps(report.to_dict(), indent=2), file=sys.stderr)
            raise SystemExit(1) from exc
    else:
        keys = json.loads(keys_path.read_text(encoding="utf-8"))
        report.session_keys_expires_at = keys.get("session_keys_expires_at")

    gate = run_auth_gate(host, keys, debug=debug, check_notify=check_notify)
    report.auth_ok = gate.auth_ok
    report.confirm_signin = gate.confirm_signin
    report.get_nonce = gate.get_nonce
    report.get_session_random = gate.get_session_random
    report.notify_stream_ok = gate.notify_stream_ok
    if gate.error:
        report.error = gate.error

    if not report.auth_ok:
        print(json.dumps(report.to_dict(), indent=2), file=sys.stderr)
        raise SystemExit(1)
    return keys, report
