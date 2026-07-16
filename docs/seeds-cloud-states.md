# Sony Seeds cloud state reads (gRPC notify-only settings)

> **Credit:** [@mafredri](https://github.com/mafredri) discovered and proved this path via socket tracing and direct API calls ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)). BRAVIA Connect reads settings that local gRPC cannot return from `GET /devices/{device_id}/states`. This document records HA’s probe validation and integration decision ([#139](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/139)).

## Problem

On fw `001.454`, paths such as DRC, DSEE Ultimate, 360SSM height, and eARC accept **local gRPC writes** (`ExecCommandWithAuth`) but are **not readable** via bulk/single `GetStatesWithAuth` or the notify stream. HA entities for these settings would stay stale without a read path.

Previously, gRPC transport used **TCP JSON-RPC** (`:33336`) to seed notify-only entity state. That hybrid breaks on models where TCP is blocked (e.g. **HT-A8** per [README](../README.md)).

## API contract

| Item | Value |
|------|--------|
| Endpoint | `GET https://v1.api.iot.seeds.services/devices/{device_id}/states` |
| Auth | `Authorization: Bearer {access_token}` (same OAuth token in `CONF_GRPC_KEYS`) |
| Headers | Reuse `_IOT_HEADERS_BASE` from [`grpc/credentials.py`](../custom_components/bravia_quad/grpc/credentials.py) (`x-api-key`, BRAVIA Connect user-agent) |
| Session keys | **Not** used for this call — OAuth access token only |

### Response shape (HT-A9M2, live probe 2026-07-06)

Top-level keys: `connectivity`, `states`, `timestamp`.

`states` is an array of `{ "name": "<grpc_path>", "value": <bool|int|string> }` objects. Field names match gRPC dot paths directly (e.g. `sound_setting.drc`, `speaker_sound_setting.360ssm_height`).

Example (redacted):

```json
{
  "connectivity": true,
  "timestamp": "...",
  "states": [
    { "name": "sound_setting.drc", "value": "auto" },
    { "name": "sound_setting.dsee_ultimate", "value": false },
    { "name": "speaker_sound_setting.360ssm_height", "value": "mid" },
    { "name": "sound_setting.sound_effect", "value": "Neural:X" },
    { "name": "system_setting.dimmer", "value": "dark" }
  ]
}
```

Observed latency: ~110 ms (single GET, US Seeds WW endpoint).

## Field mapping

Seeds values are stored in the gRPC notify cache **as returned** (gRPC-native types). Entity code normalizes on read via [`grpc_value_normalize.py`](../custom_components/bravia_quad/grpc_value_normalize.py).

| gRPC path | Seeds present (probe) | HA entity | Notes |
|-----------|----------------------|-----------|-------|
| All `NOTIFY_ONLY_GRPC_PATHS` (incl. dimmer) | Yes | switch/select | Primary gRPC-mode read path |
| `system_setting.earc` | Yes | switch | Bool in Seeds; gRPC switch on/off (not tri-state) |
| `sound_setting.sound_effect` | Yes | select | Not in notify-only list; unreadable via GetStates |
| `system_setting.dimmer` | Yes | select | Notify-only; Seeds seed when `grpc_seeds_poll` enabled |
| Empty-wire GetStates bools (`mute`, `sound_setting.night_mode`, `sound_setting.sound_field`, `sound_setting.voice_mode`) | Yes | switch / media mute | Local GetStates returns key with `None` on fw 001.454; Seeds supplies the real bool when `grpc_seeds_poll` is on (TCP seed when Seeds is off) |

Enum strings match gRPC exec values (`"auto"`, `"mid"`, `"Neural:X"`, etc.). Display brightness uses `"bright"`, `"dark"`, and `"off"`. Booleans are JSON `true`/`false` (e.g. DSEE, eARC enabled).

## Operational behavior

| Topic | Behavior |
|-------|----------|
| **When fetched** | Startup/reconnect backfill (unset-only); debounced force refresh (~2 s) after a local gRPC `playback_control.no_audio` notify when `grpc_seeds_poll` is on (pipeline-reset signal when audio settings change — value is ignored). HA-initiated writes trust the local exec cache and are not immediately re-read from Seeds (cloud lags; a write guard skips force-overwrite of that path for a few seconds) |
| **Offline / Seeds error** | Log at debug; fall back to HA state restore + last successful exec write — **no TCP fallback in gRPC mode** |
| **Polling frequency** | Event-driven only: one GET at backfill and debounced `no_audio`-triggered refresh (not periodic polling) |
| **Caveat** | With nothing playing, a second app-side change may not emit another `no_audio` until playback resumes — HA may lag until the next pipeline reset |
| **Privacy** | Device settings sent to Sony cloud (same as BRAVIA Connect); opt-in via integration option `grpc_seeds_poll` |

## Decision (implement)

| Criterion | Result |
|-----------|--------|
| API stable + maps cleanly | **Pass** — `{name,value}` array matches gRPC paths |
| Post-exec convergence | **Pass** — DRC toggle visible in Seeds within 3 s |
| HT-A8 / TCP-blocked models | **Pass** — universal read path without `:33336` |
| Partial coverage | Allowlisted Seeds seed paths present (notify-only + `sound_effect` + empty-wire bools) |

**Recommendation:** Enable Seeds cloud reads in gRPC transport (opt-in default `false` until users validate; target default-on once stable). Replace TCP seed in [`async_backfill_entity_paths()`](../custom_components/bravia_quad/bravia_grpc_client.py) when enabled. Do **not** replace local gRPC writes.

## Related docs

- [grpc-auth-lifecycle.md](grpc-auth-lifecycle.md) — OAuth tokens and notify-only reads
- [grpc-tcp-mapping.md](grpc-tcp-mapping.md) — entity seeding order (gRPC mode → Seeds)
- [sony-grpc-reference.md](sony-grpc-reference.md) — notify-only path table
