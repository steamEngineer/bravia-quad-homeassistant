# Sony gRPC reference (Bravia Theatre)

Documentation index: [docs/README.md](README.md)

Quick reference for the BRAVIA Connect gRPC transport used in gRPC mode. See also [scripts/grpc/README.md](../scripts/grpc/README.md) for optional CLI key extraction.

## Service

- **Endpoint:** `{host}:55051` (h2c, no TLS)
- **Service:** `jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService`
- **Auth:** Sony Seeds session keys (`device_id`, `key_id`, `session_key`, `hmac_key`)

## Primary RPCs

| RPC | Purpose |
|-----|---------|
| `GetStatesWithAuth` | Snapshot of field paths → values; seeds notify cache |
| `StartNotifyStates` | Push stream of field path updates |
| `ExecCommandWithAuth` | Write a single field path (`int_value`, `bool_value`, or `string_value`) |

Wire formats for GetStates and ExecCommand differ from the checked-in `.proto`; see `grpc/get_states_request.py` and `grpc/exec_command_request.py`.

## Field paths

177+ field paths are captured in `grpc/all_field_paths.txt`. Mapped HA entities use a subset documented in [grpc-tcp-mapping.md](grpc-tcp-mapping.md).

Common paths:

| Path | Type | HA use |
|------|------|--------|
| `power` | bool | Media player / switch |
| `volume` | int | Media player / number |
| `mute` | bool | Media player |
| `playback_control.function` | string | Source select / media player |
| `sound_setting.drc` | string enum | DRC select |
| `sound_setting.auto_volume` | bool | Auto Volume switch |
| `system_setting.ipv4_address` | string | IP sensor |

## Exec encoding notes

Bool paths verified for ExecCommand wire format include `power`, `mute`, `sound_setting.night_mode`, `sound_setting.sound_field`, `sound_setting.voice_mode`, `sound_setting.auto_volume`, and related system toggles. Enum selects use `string_value`; level sliders use `int_value`.

## Session lifecycle

Session keys expire after ~24 hours. The integration refreshes OAuth access tokens and fetches new session keys automatically when a refresh token is available. Reconfigure the integration if refresh fails. BRAVIA Connect may evict HA sessions; the reconnect loop re-seeds state from GetStates after reconnect.

## Notify-only paths

Some paths (including `sound_setting.drc`) are **writable** via `ExecCommandWithAuth` but are **not** in the Connect GetStates field list mirrored by HA (`all_field_paths.txt`). Bulk GetStates, single-path GetStates, and notify deltas do not reliably return these values on current firmware.

HA handles this by:

1. **Write** notify-only paths via ExecCommand (DRC, Auto Volume, etc.).
2. **Read** via TCP seed ([`grpc_tcp_seed.py`](../custom_components/bravia_quad/grpc_tcp_seed.py)) for paths with TCP feature mappings, plus HA state restore when TCP is unavailable.
3. **Treat BRAVIA Connect UI parity as best-effort** — the app may show values from sources other than live gRPC reads.

DSEE Ultimate and 360SSM height have no confirmed TCP read feature on tested firmware; wiring is deferred until a stable read path is confirmed.
