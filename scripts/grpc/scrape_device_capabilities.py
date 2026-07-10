#!/usr/bin/env python3
"""Scrape device capabilities for building device-specific HA entity scoping.

Contributor runbook
---------------------
1. One-time Sony OAuth (opens browser)::

       uv run python scripts/grpc/get_session_keys.py -o scripts/grpc/session_keys.json

2. Stop Home Assistant if running (only one :55051 gRPC client at a time)::

       pkill -f "hass --config $(pwd)/config"

3. Run scrape::

       uv run python scripts/grpc/scrape_device_capabilities.py <DEVICE_IP> \\
         --refresh --out ./scrape-reports

4. Attach the generated ``.md`` and ``.json`` files to a GitHub issue.

Prerequisites: device on LAN, Sony account linked in BRAVIA Connect, ``uv sync``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import grpc

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_GRPC = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))
sys.path.insert(0, str(_SCRIPTS_GRPC))

from bravia_quad.const import DEFAULT_PORT  # noqa: E402
from bravia_quad.grpc.client import BraviaGrpcClient  # noqa: E402
from bravia_quad.grpc.credentials import get_device_states  # noqa: E402
from bravia_quad.grpc.get_capabilities_response import (  # noqa: E402
    get_capabilities_method,
)
from bravia_quad.grpc_mapping import (  # noqa: E402
    NOTIFY_ONLY_GRPC_PATHS,
    entity_critical_grpc_paths,
    mappings_with_tcp_feature,
)
from device_scrape_report import (  # noqa: E402
    build_full_report,
    decode_get_capabilities_response,
    flatten_seeds_states,
    redact_report,
    render_markdown,
    report_filename_stem,
)
from scrape_auth_gate import DEFAULT_KEYS_PATH, gate_or_exit  # noqa: E402

_RPC_GET_CAPABILITIES = get_capabilities_method()


def _print_banner() -> None:
    print(
        "\n*** Stop Home Assistant before running — only one :55051 client at a time ***\n",
        file=sys.stderr,
    )


def _unary(
    client: BraviaGrpcClient,
    method: str,
    request: bytes,
    *,
    timeout: float = 15.0,
) -> tuple[bytes | None, str | None, float]:
    if not client.channel:
        return None, "no channel", 0.0
    call = client.channel.unary_unary(
        method,
        request_serializer=lambda payload: payload,
        response_deserializer=lambda payload: payload,
    )
    started = time.monotonic()
    try:
        response = call.future(request, timeout=timeout).result()
    except grpc.RpcError as exc:
        return None, f"{exc.code().name}: {exc.details()}", time.monotonic() - started
    return response, None, time.monotonic() - started


def _connect_client(host: str, keys: dict[str, Any]) -> BraviaGrpcClient:
    client = BraviaGrpcClient(host)
    client.connect()
    ok = client.authenticate(
        session_key=keys.get("session_key"),
        hmac_key=keys["hmac_key"],
        key_id=keys["key_id"],
        device_id=keys.get("device_id"),
    )
    if not ok:
        msg = "gRPC authenticate() failed"
        raise RuntimeError(msg)
    return client


def probe_get_capabilities(
    host: str,
    keys: dict[str, Any],
) -> dict[str, Any]:
    """Fetch GetCapabilities JSON from device."""
    client = _connect_client(host, keys)
    try:
        raw, err, latency = _unary(client, _RPC_GET_CAPABILITIES, b"")
        decoded = decode_get_capabilities_response(raw) if raw else {}
        cap_json: dict[str, Any] | None = None
        if decoded.get("text"):
            try:
                cap_json = json.loads(decoded["text"])
            except json.JSONDecodeError as exc:
                decoded["json_error"] = str(exc)
        return {
            "ok": err is None,
            "error": err,
            "latency_s": round(latency, 4),
            "decoded": decoded,
            "capabilities_json": cap_json,
        }
    finally:
        client.disconnect()


def scrape_grpc_snapshot(host: str, keys: dict[str, Any]) -> dict[str, Any]:
    """Bulk GetStates + single-path backfill for entity-critical paths."""
    client = _connect_client(host, keys)
    try:
        bulk = client.get_states_app_sequence() or {}
        client._notify_state.update(bulk)
        bulk_resolved = 0
        notify_only_set = set(NOTIFY_ONLY_GRPC_PATHS)
        for path in sorted(entity_critical_grpc_paths()):
            if path in notify_only_set:
                continue
            if client.notify_state.get(path) is not None:
                continue
            result = client.get_states_single_path(
                path, use_signed_auth=True, quiet=True
            )
            if result and result.get(path) is not None:
                client._notify_state.update(result)
                bulk_resolved += 1
        return {
            "bulk_fields": len(bulk),
            "bulk_single_path_resolved": bulk_resolved,
            "snapshot": dict(client.notify_state),
        }
    finally:
        client.disconnect()


def scrape_seeds(keys: dict[str, Any]) -> dict[str, Any]:
    """Fetch Sony Seeds cloud states."""
    access_token = keys.get("access_token")
    device_id = keys.get("device_id")
    if not access_token or not device_id:
        return {
            "ok": False,
            "error": "keys file missing access_token or device_id",
            "flat": {},
            "latency_ms": None,
        }
    started = time.monotonic()
    try:
        raw = get_device_states(device_id, access_token)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "flat": {},
            "latency_ms": None,
        }
    elapsed_ms = (time.monotonic() - started) * 1000
    flat = flatten_seeds_states(raw)
    return {
        "ok": True,
        "error": None,
        "flat": flat,
        "latency_ms": round(elapsed_ms, 2),
    }


def scrape_tcp_reachable(host: str, *, port: int = DEFAULT_PORT) -> dict[str, Any]:
    """Probe whether TCP IP-control port accepts a connection (no feature reads)."""
    import socket

    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=3.0):
            pass
    except OSError as exc:
        return {
            "reachable": False,
            "port": port,
            "error": str(exc),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }
    return {
        "reachable": True,
        "port": port,
        "error": None,
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
    }


def scrape_http_identity(host: str) -> dict[str, Any]:
    """Fetch model/firmware from HTTP management API (port 54545)."""
    import aiohttp
    from bravia_quad.bravia_http_client import BraviaHttpClient

    async def _run() -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            client = BraviaHttpClient(host, session)
            info = await client.async_get_system_info()
            return {
                "ok": bool(info.model_name or info.version),
                "model_id": info.model_name,
                "firmware": info.version,
                "error": None,
            }

    try:
        return asyncio.run(_run())
    except (OSError, TimeoutError, aiohttp.ClientError, RuntimeError) as exc:
        return {
            "ok": False,
            "model_id": None,
            "firmware": None,
            "error": str(exc),
        }


def scrape_tcp_parity(host: str) -> dict[str, Any]:
    """Best-effort TCP read for mappings with tcp_feature."""
    from bravia_quad.bravia_quad_client import BraviaQuadClient
    from bravia_quad.const import DEFAULT_NAME

    tcp = BraviaQuadClient(host, DEFAULT_NAME)
    rows: list[dict[str, Any]] = []

    async def _run() -> None:
        await tcp.async_connect()
        for mapping in mappings_with_tcp_feature():
            if mapping.tcp_feature is None:
                continue
            try:
                raw = await tcp.async_get_tcp_feature(mapping.tcp_feature)
            except (ConnectionError, OSError, TimeoutError) as exc:
                rows.append(
                    {
                        "grpc_path": mapping.grpc_path,
                        "tcp_feature": mapping.tcp_feature,
                        "error": str(exc),
                    }
                )
                continue
            rows.append(
                {
                    "grpc_path": mapping.grpc_path,
                    "tcp_feature": mapping.tcp_feature,
                    "tcp_raw": raw,
                    "present": raw is not None,
                }
            )

    try:
        asyncio.run(_run())
    except (ConnectionError, OSError, TimeoutError) as exc:
        return {"ok": False, "error": str(exc), "rows": rows}
    finally:

        async def _disconnect() -> None:
            await tcp.async_disconnect()

        with contextlib.suppress(Exception):
            asyncio.run(_disconnect())

    return {
        "ok": True,
        "error": None,
        "rows": rows,
        "feature_count": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape Bravia device capabilities for HA entity scoping"
    )
    parser.add_argument("host", help="Device IP or hostname")
    parser.add_argument(
        "--keys",
        type=Path,
        default=DEFAULT_KEYS_PATH,
        help="Sony Seeds session_keys.json",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh OAuth tokens before scrape",
    )
    parser.add_argument(
        "--tcp",
        action="store_true",
        help="Also poll TCP features (port 33336)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("scrape-reports"),
        help="Output directory for JSON and Markdown reports",
    )
    parser.add_argument(
        "--include-pii",
        action="store_true",
        help="Keep serial/MAC/IP in output (default: redact for sharing)",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    _print_banner()

    keys, auth_report = gate_or_exit(
        args.host,
        args.keys,
        refresh=args.refresh,
        debug=args.debug,
        check_notify=False,
    )

    print(f"Auth OK — scraping {args.host} …", file=sys.stderr)

    cap_result = probe_get_capabilities(args.host, keys)
    if not cap_result.get("ok"):
        print(
            f"Warning: GetCapabilities failed: {cap_result.get('error')}",
            file=sys.stderr,
        )

    grpc_result = scrape_grpc_snapshot(args.host, keys)
    seeds_result = scrape_seeds(keys)
    if not seeds_result.get("ok"):
        print(
            f"Warning: Seeds scrape failed: {seeds_result.get('error')}",
            file=sys.stderr,
        )

    tcp_reachable = scrape_tcp_reachable(args.host)
    http_identity = scrape_http_identity(args.host)
    tcp_parity = scrape_tcp_parity(args.host) if args.tcp else None

    report = build_full_report(
        host=args.host,
        auth_gate=auth_report.to_dict(),
        capabilities_raw=cap_result,
        capabilities_json=cap_result.get("capabilities_json"),
        grpc_snapshot=grpc_result["snapshot"],
        seeds_flat=seeds_result.get("flat") or {},
        seeds_latency_ms=seeds_result.get("latency_ms"),
        scrape_meta={
            "grpc_bulk_fields": grpc_result["bulk_fields"],
            "grpc_backfill_resolved": grpc_result["bulk_single_path_resolved"],
            "seeds_ok": seeds_result.get("ok"),
            "seeds_error": seeds_result.get("error"),
            "get_capabilities_ok": cap_result.get("ok"),
            "tcp_enabled": args.tcp,
            "tcp_reachable": tcp_reachable.get("reachable"),
            "http_identity_ok": http_identity.get("ok"),
            "http_identity_error": http_identity.get("error"),
        },
        tcp_parity=tcp_parity,
        tcp_reachable=tcp_reachable,
        http_identity=http_identity,
    )

    output_report = redact_report(report, include_pii=args.include_pii)
    stem = report_filename_stem(report["hardware_profile"])
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / f"{stem}.json"
    md_path = args.out / f"{stem}.md"

    json_path.write_text(
        json.dumps(output_report, indent=2, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(output_report), encoding="utf-8")

    hw = report["hardware_profile"]
    diffs = report["diffs"]
    print(f"\nModel: {hw.get('model_id')}  Firmware: {hw.get('firmware')}")
    print(
        f"Entity coverage: {diffs.get('entity_paths_with_live_value')}/"
        f"{diffs.get('entity_paths_total')}"
    )
    print(f"Capability paths: {diffs.get('capability_path_count')}")
    print(f"Unmapped candidates: {len(diffs.get('unmapped_new_candidates') or [])}")
    print(f"\nWrote:\n  {json_path}\n  {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
