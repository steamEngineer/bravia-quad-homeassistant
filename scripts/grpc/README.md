# Bravia gRPC standalone tools

Optional CLI helpers for Sony Seeds OAuth and session key extraction. The Home Assistant integration performs the same OAuth flow during setup — use this script only for local debugging.

## Home Assistant integration

Setup chooses **gRPC** (recommended, BRAVIA Connect) or **TCP** (legacy IP control) at config time — not both. The setup wizard defaults to gRPC. See [docs/configuration.md](../../docs/configuration.md#transport-modes) for transport details.

| Doc | Purpose |
|-----|---------|
| [sony-grpc-reference.md](../../docs/sony-grpc-reference.md) | RPC + credential reference |
| [grpc-tcp-mapping.md](../../docs/grpc-tcp-mapping.md) | Entity mapping table |

## CLI session keys

Run from repo root:

```bash
# OAuth → write keys to a local file (never commit the output)
uv run python scripts/grpc/get_session_keys.py -o /tmp/session_keys.json
```

The script opens a browser for Sony sign-in, lists your Bravia devices, and writes `device_id`, `session_key`, `hmac_key`, and OAuth tokens to the output file. See [`session_keys_example.json`](session_keys_example.json) for the expected shape (keys only, no live credentials).

## Device capability scrape

For a new Bravia model/firmware, scrape local gRPC state plus Seeds cloud reads into a redacted report you can attach to a GitHub issue. Maintainers use the JSON to compare capability coverage and Seeds-only paths against the HA mapping table.

GetStates uses the device-safe path set: every capability with `get: true`, excluding paths marked `command_independence.getstates_request` (the device rejects the whole batch if any such path is included). That pulls topology, battery, and other capability-only fields that the older HA path-list scrape omitted. Single-path backfill still covers mapped entities plus speaker status/history and `battery.*` when needed.

TCP `:33336` reachability is always recorded. Connection refused is normal on gRPC-only models that do not advertise `system_setting.external_control` (for example Theatre Trio HT-A8). Optional `--tcp` also dumps TCP feature reads when that port is open.

HTTP `:54545` identity (`system.version` / `system.modelname`) is always scraped. By default the scrape also runs a read-only FCGI **feature catalog** (HA + management-UI + TCP-name candidates; skips `fw.upload` / `fw.request_update` / `fw.update`). Use `--skip-http-catalog` to omit it for a faster gRPC-only pass.

When HTTP identity (`:54545`) and gRPC `system_setting.model_name` are missing, the scrape falls back to Seeds IoT `/devices` (`identified_model_name` / firmware) for the report filename and hardware profile.

```bash
# One-time OAuth (if you do not already have session_keys.json)
uv run python scripts/grpc/get_session_keys.py -o scripts/grpc/session_keys.json

# Stop Home Assistant first — only one :55051 gRPC client at a time
uv run python scripts/grpc/scrape_device_capabilities.py <DEVICE_IP> \
  --refresh --out ./scrape-reports
```

Attach both generated files (`.md` summary and `.json` full report) to the issue. Output is PII-redacted by default: serial/MAC/IP/device id, now-playing metadata (title/artist/album/artwork/playlist), speaker GPS layout, and HTTP catalog LAN/Wi-Fi fields (device name, MAC, IP, SSID lists, AirPlay name, WPS PIN, public key). Use `--include-pii` only for local debugging.
