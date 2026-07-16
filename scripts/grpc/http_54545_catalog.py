"""HTTP :54545 FCGI feature catalog for device capability scrapes.

Read-only ``http_get`` sweep of the Theatre management API. Never POSTs
firmware write paths (``fw.upload`` / ``fw.request_update`` / ``fw.update``).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

HTTP_PORT = 54545
HTTP_PATH = "/fcgi-bin/request.fcgi"
DEFAULT_TIMEOUT = 10.0
DEFAULT_DELAY = 0.05

# Never POST these — UI write/side-effect paths (even as http_get).
SKIP_HTTP_GET: frozenset[str] = frozenset(
    {
        "fw.upload",
        "fw.request_update",
        "fw.update",
    }
)

# Feature values redacted in shareable scrape reports (LAN / Wi-Fi / names).
HTTP_PII_FEATURES: frozenset[str] = frozenset(
    {
        "network.devicename",
        "network.macaddress_wired",
        "network.macaddress_wireless",
        "inet4.ipaddress",
        "inet4.subnetmask",
        "inet4.gateway",
        "inet4.dns1",
        "inet4.dns2",
        "inet4.conf_ipaddress",
        "inet4.conf_subnetmask",
        "inet4.conf_gateway",
        "inet4.conf_dns1",
        "inet4.conf_dns2",
        "inet6.ipaddress",
        "inet6.temporaryaddress",
        "inet6.linklocalipv6address",
        "inet6.gateway",
        "inet6.dns1",
        "inet6.dns2",
        "ssid.name",
        "wlan.esslist",
        "wlan.scan",
        "airplay.accessoryname",
        "system.publickey",
        "wps.refreshpin",
    }
)

HA_FEATURES: list[str] = [
    "system.version",
    "system.modelname",
    "network.devicename",
    "network.connectiontype",
    "network.internet",
    "network.macaddress_wired",
    "network.macaddress_wireless",
    "inet4.ipaddress",
    "inet6.ipaddress",
    "wlan.strength",
    "fw.check_update",
]

UI_FEATURES: list[str] = [
    "system.version",
    "system.modelname",
    "system.publickey",
    "network.devicename",
    "network.connectiontype",
    "network.internet",
    "network.macaddress_wired",
    "network.macaddress_wireless",
    "network.applyconfig",
    "ssid.name",
    "ssid.auth",
    "wlan.strength",
    "wlan.scan",
    "wlan.esslist",
    "wlan.connect",
    "wlan.connect_manual",
    "wlan.reconnect",
    "wps.refreshpin",
    "wps.connectpbc",
    "wps.connectpin",
    "inet4.dhcp",
    "inet4.ipaddress",
    "inet4.subnetmask",
    "inet4.gateway",
    "inet4.dns1",
    "inet4.dns2",
    "inet4.conf_ipaddress",
    "inet4.conf_subnetmask",
    "inet4.conf_gateway",
    "inet4.conf_dns1",
    "inet4.conf_dns2",
    "inet6.enabled",
    "inet6.dhcp",
    "inet6.ipaddress",
    "inet6.temporaryaddress",
    "inet6.linklocalipv6address",
    "inet6.gateway",
    "inet6.dns1",
    "inet6.dns2",
    "airplay.accessoryname",
    "airplay.accessoryname_status",
    "fw.check_update",
]

TCP_FEATURES: list[str] = [
    "main.power",
    "main.volumestep",
    "main.input",
    "main.rearvolumestep",
    "main.bassstep",
    "main.mute",
    "audio.voiceenhancer",
    "audio.soundfield",
    "audio.nightmode",
    "audio.drangecomp",
    "audio.aav",
    "audio.dualmono",
    "audio.imaxmode",
    "audio.avsync",
    "audio.voicezoom3",
    "audio.voicezoom3step",
    "audio.360ssm",
    "hdmi.cec",
    "hdmi.passthrough",
    "hdmi.standbylink",
    "hdmi.audioreturnchannel",
    "system.autostandby",
    "system.autoupdate",
    "system.serialnumber",
    "system.externalcontrol",
    "system.netbtstandby",
    "system.timezone",
    "system.temperature",
    "system.version",
    "system.modeltype",
    "system.manufacturer",
    "system.devicename",
    "system.destination",
    "system.language",
    "network.macaddress",
    "network.mode",
    "network.ipaddress",
    "network.dhcp",
    "bluetooth.connectionquality",
    "tv.avsync",
]

EXTRA_FEATURES: list[str] = [
    "system.modelnumber",
    "system.productname",
    "system.hwversion",
    "system.swversion",
    "system.firmware",
    "system.build",
    "network.hostname",
    "fw.version",
    "fw.status",
    "fw.check",
]

_SIDE_EFFECT_GET: frozenset[str] = frozenset(
    {
        "network.applyconfig",
        "wlan.connect",
        "wlan.connect_manual",
        "wlan.reconnect",
        "wps.connectpbc",
        "wps.connectpin",
    }
)


def classify_value(value: Any) -> str:
    """Classify a single feature value from http_get_result."""
    if value is None:
        return "missing"
    if value == "ERR":
        return "err"
    if value == "NAK":
        return "nak"
    if value == "ACK":
        return "ack"
    if value == "":
        return "empty"
    return "value"


def post_fcgi(
    host: str, payload: dict[str, Any], timeout: float
) -> tuple[int | None, Any, str | None]:
    """POST JSON to request.fcgi. Returns (status, parsed_or_text, error)."""
    url = f"http://{host}:{HTTP_PORT}{HTTP_PATH}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
            try:
                return status, json.loads(body), None
            except json.JSONDecodeError:
                return status, body, "non_json"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, f"http_{exc.code}"
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        return None, None, str(exc)


def probe_feature(
    host: str, feature: str, timeout: float, delay: float
) -> dict[str, Any]:
    """http_get a single feature and classify the result."""
    if delay > 0:
        time.sleep(delay)
    status, parsed, err = post_fcgi(
        host,
        {"type": "http_get", "packet": [[feature]]},
        timeout,
    )
    row: dict[str, Any] = {
        "feature": feature,
        "http_status": status,
        "error": err,
        "class": "transport_error",
        "value": None,
    }
    if err and status is None:
        return row
    if not isinstance(parsed, dict):
        row["class"] = "non_json" if err == "non_json" else "unexpected"
        return row
    if parsed.get("type") != "http_get_result":
        row["class"] = "unexpected_type"
        return row
    packet = parsed.get("packet")
    if not packet or packet == [None] or packet[0] is None:
        row["class"] = "empty_packet"
        return row
    try:
        item = packet[0][0]
    except (IndexError, TypeError, KeyError):
        row["class"] = "malformed_packet"
        return row
    value = item.get("value") if isinstance(item, dict) else None
    row["value"] = value
    row["class"] = classify_value(value)
    return row


def path_probe(host: str, path: str, timeout: float) -> dict[str, Any]:
    """GET a path on :54545 and summarize status/content-type."""
    url = f"http://{host}:{HTTP_PORT}{path}"
    req = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return {
                "path": path,
                "http_status": resp.status,
                "content_type": resp.headers.get("Content-Type"),
                "server": resp.headers.get("Server"),
            }
    except urllib.error.HTTPError as exc:
        return {
            "path": path,
            "http_status": exc.code,
            "content_type": exc.headers.get("Content-Type") if exc.headers else None,
            "error": f"http_{exc.code}",
        }
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        return {"path": path, "http_status": None, "error": str(exc)}


def candidate_features(*, include_tcp: bool = True) -> list[tuple[str, str]]:
    """Deduped (feature, source) list preserving first-seen source priority."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    sources: list[tuple[str, list[str]]] = [
        ("ha", HA_FEATURES),
        ("ui", UI_FEATURES),
        ("extra", EXTRA_FEATURES),
    ]
    if include_tcp:
        sources.insert(2, ("tcp", TCP_FEATURES))
    for source, items in sources:
        for feat in items:
            if feat in seen or feat in SKIP_HTTP_GET:
                continue
            seen.add(feat)
            out.append((feat, source))
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Group features by classification."""
    by_class: dict[str, list[str]] = {}
    values: dict[str, Any] = {}
    for row in rows:
        by_class.setdefault(row["class"], []).append(row["feature"])
        if row["class"] == "value":
            values[row["feature"]] = row["value"]
    return {
        "counts": {k: len(v) for k, v in sorted(by_class.items())},
        "by_class": {k: sorted(v) for k, v in sorted(by_class.items())},
        "values": values,
    }


def scrape_http_catalog(
    host: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
    include_tcp: bool = True,
    progress: bool = False,
) -> dict[str, Any]:
    """Run the :54545 feature catalog and return a report section dict."""
    candidates = candidate_features(include_tcp=include_tcp)
    if progress:
        print(
            f"HTTP :54545 catalog — {len(candidates)} features …",
            flush=True,
        )

    path_map = [
        path_probe(host, p, timeout)
        for p in (
            "/",
            "/menu.html",
            "/settings/devicedetails.html",
            "/fcgi-bin/request.fcgi",
            "/www/jacket/",
        )
    ]

    rows: list[dict[str, Any]] = []
    for feature, source in candidates:
        if progress:
            print(f"  {feature} ({source})...", end="", flush=True)
        row = probe_feature(host, feature, timeout, delay)
        row["source"] = source
        rows.append(row)
        if progress:
            print(f" {row['class']}", flush=True)

    ui_batch = [
        f for f in UI_FEATURES if f not in SKIP_HTTP_GET and f not in _SIDE_EFFECT_GET
    ][:12]
    batch_status, batch_parsed, batch_err = post_fcgi(
        host,
        {"type": "http_get", "packet": [ui_batch]},
        timeout,
    )
    # Drop raw packet body from batch (values live in per-feature rows).
    batch = {
        "features": ui_batch,
        "http_status": batch_status,
        "error": batch_err,
        "response_type": (
            batch_parsed.get("type") if isinstance(batch_parsed, dict) else None
        ),
    }

    summary = summarize(rows)
    tcp_hits = [
        r["feature"]
        for r in rows
        if r.get("source") == "tcp" and r["class"] in ("value", "nak")
    ]
    return {
        "ok": True,
        "port": HTTP_PORT,
        "path": HTTP_PATH,
        "skipped": sorted(SKIP_HTTP_GET),
        "path_map": path_map,
        "feature_count": len(rows),
        "features": rows,
        "summary": summary,
        "batch_sample": batch,
        "tcp_http_overlap": tcp_hits,
        "server": next(
            (p.get("server") for p in path_map if p.get("server")),
            None,
        ),
    }
