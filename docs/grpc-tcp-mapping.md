# gRPC ↔ TCP entity mapping

Documentation index: [docs/README.md](README.md)

Home Assistant **gRPC transport mode** exposes entities via mapping-driven factories (`grpc_mapped_entities.py`) and the gRPC media player (`grpc_media_player.py`). Unique ID suffixes match TCP mode where features are bridged so automations survive transport re-add.

## Architecture

- **`grpc_mapping.py`** — canonical path → TCP feature → HA platform table
- **`grpc_entity_registry.py`** — translation keys and unique ID suffixes aligned with TCP
- **`grpc_value_normalize.py`** — read (`normalize_grpc_value`) and write (`denormalize_for_exec`) value conversion
- **`grpc_mapped_entities.py`** — generic switch/select/number/sensor factories
- **`grpc_media_player.py`** — media player (power, volume, mute, source, sound field mode, now-playing metadata, playback info attributes, streaming transport controls)

Input source and gRPC sound field mode (`sound_setting.sound_effect`) are exposed only on the media player — standalone `select.*_input` and `select.*_sound_effect` entities are removed on setup.

ExecCommand and StartNotifyStates share the same field paths. Writable entities call `async_exec_command`; state updates arrive on the notify stream.

## Media player metadata (gRPC only)

Read-only `extra_state_attributes` on the media player (filtered by active source):

| gRPC path | Attribute | Shown when |
|-----------|-----------|------------|
| `playback_control.audio_format` | `audio_format` | TV / HDMI |
| `playback_control.audio_channel` | `audio_channel` | TV / HDMI |
| `playback_control.sampling_rate` | `sampling_rate` | TV / HDMI |
| `playback_control.is_360ra` | `is_360ra` | Any |
| `playback_control.upmixer` | `upmixer` | Any |
| `playback_control.virtualizer` | `virtualizer` | Any |
| `playback_control.bt_codec` | `bt_codec` | Bluetooth |
| `playback_control.bt_device_name` | `bt_device_name` | Bluetooth |
| `playback_control.bt_signal_strength` | `bt_signal_strength` | Bluetooth |
| `playback_control.hdmi_error` | `hdmi_error` | TV / HDMI |
| `playback_control.no_audio` | `no_audio` | TV / HDMI |
| `playback_control.spotify.status` | `spotify_status` | Spotify |
| `playback_control.function.unavailable_reason` | `source_unavailable_reason` | When set |

Dynamic source list: when the device publishes `playback_control.function.available_values`, the media player updates `source_list` (falls back to static `INPUT_OPTIONS`).

Sound field mode: `SELECT_SOUND_MODE` on the media player maps to `sound_setting.sound_effect` (Dolby Speaker Virtualizer, Neural:X, 360SSM).

## Playback transport (gRPC only)

Verified on HT-A9M2 (fw 001.454). Spotify and AirPlay share the same command map. AirPlay reports `playback_control.function=airplay` on the wire; HA normalizes that to `airplay2` for source display and TCP parity. AirPlay cannot be selected via ExecCommand — it appears when a client casts to the device.

| HA service | ExecCommand path | Value | Status |
|------------|------------------|-------|--------|
| `media_player.media_play` | `playback_control.playback_command` | `string_value=play` | Confirmed |
| `media_player.media_pause` | `playback_control.playback_command` | `string_value=pause` | Confirmed |
| `media_player.media_next_track` | `playback_control.playback_command` | `string_value=next` | Confirmed |
| `media_player.media_previous_track` | `playback_control.playback_command` | `string_value=prev` | Confirmed (AirPlay live probe 2026-07-07) |
| — | `playback_control.playback_command` | `string_value=previous` | Exec failed (wrong token) |
| — | `playback_control.playback_command` | `string_value=stop` | Not implemented in HA |
| — | `playback_control.position` | `int_value=<seconds>` | Seek not supported |

Transport controls are advertised only when power is on and `playback_control.function` is `spotify`, `bluetooth`, or `airplay` (HA source `airplay2`). Reads (`playback_state`, title, artist, position, etc.) use the same notify paths as now-playing metadata.

AirPlay is **detect-only** in HA: `airplay2` is omitted from the selectable source list unless it is the active input.

`playback_control.playback_command.availability` is subscribed for future gating.

**Notify-only / gRPC-unreadable app settings:** Paths in `NOTIFY_ONLY_GRPC_PATHS` (DRC, 360SSM height, eARC, auto standby, etc.) accept ExecCommand writes but are **not readable** over local gRPC on fw 001.454 — single-path and bulk GetStates return `UNKNOWN`, and the notify stream never includes these paths. [@mafredri](https://github.com/mafredri) confirmed ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)) that BRAVIA Connect reads them via Seeds `GET /devices/{device_id}/states`. In gRPC mode, enable **Seeds cloud reads** (`grpc_seeds_poll`) to seed entity state without TCP — see [seeds-cloud-states.md](seeds-cloud-states.md). When Seeds is off, initial state comes from TCP seed (TCP-capable models only), HA restore, or the last Exec write cache.

## GetStates snapshot vs entity seeding

Bulk GetStates (177 paths, app-sequence with HMAC signing) parses into `notify_state` at startup. Many HA entities still show `unknown` because the device does not always return usable values:

| Category | Example paths | Bulk GetStates | Single-path GetStates | Notify at startup |
|----------|---------------|----------------|----------------------|-------------------|
| Core media | `power`, `volume`, `playback_control.function` | Real values | Same as bulk | Optional |
| Bulk bools (empty wire) | `mute`, `sound_setting.night_mode`, `sound_setting.sound_field` | Key present, value `None` | Still `None` on fw 001.454 | First delta after change |
| NOTIFY-only app settings | `sound_setting.drc`, `speaker_sound_setting.360ssm_height`, `system_setting.earc` | Absent from bulk | Fails (`UNKNOWN`) | **Not emitted** on fw 001.454 |
| Metadata | `*.availability`, `*.unavailable_reason` | Present | N/A | N/A |

Startup sequence in [`__init__.py`](../custom_components/bravia_quad/__init__.py):

1. Bulk GetStates app-sequence → seed `notify_state`
2. Per-path backfill for entity-critical paths still unset ([`async_backfill_entity_paths`](../custom_components/bravia_quad/bravia_grpc_client.py))
3. **Seeds seed** when `grpc_seeds_poll` enabled ([`grpc_seeds_seed.py`](../custom_components/bravia_quad/grpc_seeds_seed.py)) — preferred in gRPC mode (works on HT-A8 where TCP is blocked). Otherwise TCP seed ([`grpc_tcp_seed.py`](../custom_components/bravia_quad/grpc_tcp_seed.py)) for paths with `tcp_feature` mappings still unset
4. Start notify stream + path-aware warmup (up to 3s for missing entity paths)
5. Platform setup reads `notify_state`; HA restore fills gaps where device sends no initial value

NOTIFY-only paths may remain `unknown` until Seeds/TCP seed succeeds, the device pushes a notify delta, or HA restores the last persisted state — enable Seeds cloud reads on gRPC transport when possible ([seeds-cloud-states.md](seeds-cloud-states.md)).

## Corrected mappings (Phase 0)

| HA entity | TCP feature | gRPC path | Platform |
|-----------|-------------|-----------|----------|
| Dynamic Range Compressor | `audio.drangecomp` | `sound_setting.drc` | select |
| Auto Volume | `audio.aav` | `sound_setting.auto_volume` | switch |
| Bass level (no sub) | `main.bassstep` | `sound_setting.volume.bass` | select (min/mid/max) |
| Subwoofer level (with sub) | — | `sound_setting.volume.subwoofer` | number (-10…10) |
| Dual mono | `audio.dualmono` | `sound_setting.dual_mono` | select |
| BT connection quality | `bluetooth.connectionquality` | `bluetooth_setting.connection_quality` | select |
| HDMI standby link | `hdmi.standbylink` | `system_setting.hdmi_standby_through` | select |
| IP address | `network.ipaddress` | `system_setting.ipv4_address` | sensor |

**Not aliased:** `sound_setting.dts_dialog_control` (DTS Dialog Control) is a separate gRPC-only switch from DRC.

**Distinct features:** TCP **Sound field** (`sound_setting.sound_field`, bool) ≠ gRPC **Sound field mode** (`sound_setting.sound_effect`, select).

## Parity gaps

Features with no confirmed gRPC path or known semantic mismatch:

| TCP feature | Reason |
|-------------|--------|
| `hdmi.audioreturnchannel` | Proto `system_setting.earc` is bool; tri-state select unverified |
| `hdmi.passthrough` | No confirmed path (`hdmi_signal_format` candidate) |
| `audio.360ssm` | Not in field list (distinct from 360SSM height) |
| `system.temperature` | Not in field list |
| Network mode / DHCP / region / language | Not in field list |
| Bluetooth pairing button | TCP-only |

Unverified app-setting paths (`verified=False` in mapping) ship **disabled by default**: auto standby, auto update, external control, HDMI standby link, eARC.
