"""OAuth refresh + gRPC handshake gate for device capability scrape."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_GRPC = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))
sys.path.insert(0, str(_SCRIPTS_GRPC))

from bravia_quad.grpc.client import BraviaGrpcClient  # noqa: E402
from bravia_quad.grpc.credentials import refresh_credentials  # noqa: E402
from get_session_keys import write_credentials  # noqa: E402

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


def run_auth_gate(
    host: str,
    keys: dict[str, Any],
    *,
    debug: bool = False,
    check_notify: bool = False,
) -> AuthGateReport:
    """Connect and authenticate; optionally verify notify stream opens."""
    report = AuthGateReport(
        refresh_ok=True,
        auth_ok=False,
        session_keys_expires_at=keys.get("session_keys_expires_at"),
    )
    client = BraviaGrpcClient(host, debug=debug)
    try:
        client.connect()
        ok = client.authenticate(
            session_key=keys.get("session_key"),
            hmac_key=keys["hmac_key"],
            key_id=keys["key_id"],
            device_id=keys.get("device_id"),
        )
        report.auth_ok = ok
        report.confirm_signin = ok
        report.get_nonce = client.nonce is not None and client.nonce_hmac is not None
        report.get_session_random = (
            client.session_random is not None and client.auth_token is not None
        )
        if not ok:
            report.error = "gRPC authenticate() returned False"
            return report
        if not report.get_nonce:
            report.error = "GetNonce did not populate nonce/nonce_hmac"
            report.auth_ok = False
            return report
        if not report.get_session_random:
            report.error = "GetSessionRandom did not populate session tokens"
            report.auth_ok = False
            return report
        if check_notify:
            notify_ok = False
            stop = threading.Event()

            def _probe_notify() -> None:
                nonlocal notify_ok
                try:
                    for _ in client.start_notify_states():
                        notify_ok = True
                        break
                except Exception:
                    pass
                finally:
                    stop.set()

            worker = threading.Thread(target=_probe_notify, daemon=True)
            worker.start()
            worker.join(timeout=2.0)
            report.notify_stream_ok = notify_ok
    except OSError as exc:
        report.error = str(exc)
        report.auth_ok = False
    finally:
        client.disconnect()
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
