# Sony gRPC reference (Bravia Theatre)

Documentation index: [docs/README.md](README.md)

> **Contributions:** Corrections in proto schema, RPC list, and notify-only Seeds reads reported by [@mafredri](https://github.com/mafredri) ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16), cross-check in [#136](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/136)).

Quick reference for the BRAVIA Connect gRPC transport used in gRPC mode. See also [scripts/grpc/README.md](../scripts/grpc/README.md) for optional CLI key extraction.

## Service

- **Endpoint:** `{host}:55051` (h2c, no TLS)
- **Service:** `jp.co.sony.hes.ssh.controldevice.v1.ControlDeviceService`
- **Auth:** Sony Seeds session keys (`device_id`, `key_id`, `session_key`, `hmac_key`)

## Primary RPCs

| RPC | Purpose |
|-----|---------|
| `ConfirmSignin` | Device handshake step 1 |
| `ConfirmKeys` | Device handshake step 2 |
| `GetNonce` | Nonce fetch (may be optional for normal HMAC auth per @mafredri, #16) |
| `GetSessionRandom` | Yields `session_random` + initial HMAC material |
| `GetStatesWithAuth` | Snapshot of field paths → values; seeds notify cache |
| `StartNotifyStates` | Push stream of field path updates |
| `StopNotifyStates` | End notify stream |
| `ExecCommandWithAuth` | Write a single field path (`int_value`, `bool_value`, or `string_value`) |
| `GetCapabilities` | Device capability JSON |
| `GetResources` | Fetch binary resources by URI |

## Request envelope

The checked-in [`bravia_control.proto`](../custom_components/bravia_quad/grpc/bravia_control.proto) is **outdated** — an incorrectly reconstructed schema from an earlier pass. Per [@mafredri](https://github.com/mafredri)'s reflected schema ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)), authoritative auth RPCs use outer wrappers with `serialized_request + hmac` (reflected schema; local investigation reference only, not committed).

Hand encoders in [`get_states_request.py`](../custom_components/bravia_quad/grpc/get_states_request.py) and [`exec_command_request.py`](../custom_components/bravia_quad/grpc/exec_command_request.py) build the inner serialized blobs and outer HMAC envelope to match app captures.

## Error codes

Reflected schema `ErrorCode` values (local reference):

| Code | Meaning |
|------|---------|
| `KEY_NOT_REGISTERED` | Session key not registered on device |
| `HMAC_ERROR` | HMAC verification failed |
| `SESSION_RANDOM_ERROR` | Stale or invalid session random |
| `NONCE_ERROR` | Nonce mismatch |
| `DECRYPTION_ERROR` | Encrypted payload decode failed |

## Field paths

177 paths in Connect's bulk snapshot list ([`grpc/all_field_paths.txt`](../custom_components/bravia_quad/grpc/all_field_paths.txt)). Per @mafredri ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)), the device accepts valid path names individually or in flexible batches — 177 is a Connect mirror, not a hard requirement. Mapped HA entities use a subset documented in [grpc-tcp-mapping.md](grpc-tcp-mapping.md).

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

**Current integration behavior:** exec commands run signed GetStates preflight; if rolling tokens go stale after long idle notify, the client refreshes via GetSessionRandom before retrying. Per @mafredri ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)), simpler per-RPC `GetSessionRandom` + direct exec may suffice — see [grpc-auth-lifecycle.md](grpc-auth-lifecycle.md#current-implementation-vs-minimum-protocol) and [#138](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/138).

For token lifetimes, refresh triggers, handshake order, and rolling `auth_token` behavior, see **[grpc-auth-lifecycle.md](grpc-auth-lifecycle.md)** (living reference — update when auth implementation changes).

## Notify-only paths

Some paths (including `sound_setting.drc`) are **writable** via `ExecCommandWithAuth` but are **not** returned by local gRPC GetStates or the notify stream on fw `001.454`.

| Read path | Status |
|-----------|--------|
| **Write (local gRPC)** | ExecCommand — unchanged |
| **Read (local gRPC)** | Unavailable for many paths (bulk/single GetStates, notify) |
| **Read (Seeds cloud)** | @mafredri confirmed via `GET /devices/{device_id}/states` ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)); HA opt-in via `grpc_seeds_poll` — [seeds-cloud-states.md](seeds-cloud-states.md) |
| **Read (HA today, Seeds off)** | HA state restore, last successful write; TCP seed only when Seeds disabled on TCP-capable models |

DSEE Ultimate and 360SSM height have no confirmed TCP read feature on tested firmware; wiring is deferred until a stable read path is confirmed.
