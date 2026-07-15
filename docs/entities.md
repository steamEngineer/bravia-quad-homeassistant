# Entities

The integration creates entities under your Bravia Theatre device. The entity set depends on the transport chosen at setup — see [configuration.md](configuration.md#transport-modes).

*Note: `*` in entity IDs is your config entry’s unique ID.*

## TCP transport

Core entities (gRPC mode covers most of these with matching unique-ID suffixes where features are bridged). TCP also adds diagnostic extras not available over gRPC (Bluetooth pairing, HDMI passthrough, temperature, network sensors).

| Entity | Type | Description | Range/Options |
|--------|------|-------------|---------------|
| `media_player.bravia_quad_*` | Media player | Power, volume, mute, source | Sources: TV (eARC), HDMI In, Spotify, Bluetooth, AirPlay |
| `switch.bravia_quad_*_power` | Switch | Power on/off (Configuration; prefer media player for playback) | on/off |
| `number.bravia_quad_*_volume` | Number | Main volume | 0–100 |
| `number.bravia_quad_*_volume_step_interval` | Number | Delay between volume steps | 0–10000 ms |
| `number.bravia_quad_*_rear_level` | Number | Rear speaker level | −10–10 |
| `number.bravia_quad_*_bass_level` | Number | Bass level (with subwoofer) | −10–10 |
| `select.bravia_quad_*_bass_level` | Select | Bass level (without subwoofer) | MIN, MID, MAX |
| `switch.bravia_quad_*_voice_enhancer` | Switch | Voice enhancer | on/off |
| `switch.bravia_quad_*_sound_field` | Switch | Sound field processing | on/off |
| `switch.bravia_quad_*_night_mode` | Switch | Night mode | on/off |
| `switch.bravia_quad_*_hdmi_cec` | Switch | HDMI CEC | on/off |
| `switch.bravia_quad_*_auto_standby` | Switch | Auto standby | on/off |
| `select.bravia_quad_*_drc` | Select | Dynamic Range Compressor | Auto, On, Off |
| `switch.bravia_quad_*_advanced_auto_volume` | Switch | Auto Volume | on/off |
| `button.bravia_quad_*_detect_subwoofer` | Button | Re-detect subwoofer | — |
| `button.bravia_quad_*_bluetooth_pairing` | Button | Bluetooth pairing mode | — |

Only one bass-level control is writable at a time based on whether a wireless sub is currently linked. On **gRPC**, both the −10…10 subwoofer number and the min/mid/max bass select always exist: the linked control is available and the other is unavailable. Link state comes from local `speaker_connection_setting.connection_status.sw` via GetStates and notify — not Seeds, not a TCP bass-range probe.

## gRPC transport

gRPC builds entities from [grpc-tcp-mapping.md](grpc-tcp-mapping.md) plus the gRPC media player. Exact set depends on model, firmware, and subwoofer detection: mapped entities are created when the path is advertised by `GetCapabilities` (Seeds / notify-only paths are exempt and still created).

| Entity | Type | Description | Range/Options | Notes |
|--------|------|-------------|---------------|-------|
| `media_player.bravia_quad_*` | Media player | Power, volume, mute, source; sound field **mode**; now-playing; play/pause/next/prev on Spotify / Bluetooth / AirPlay | Sources: TV, HDMI, Spotify, Bluetooth; AirPlay detect-only; modes: Dolby Speaker Virtualizer, Neural:X, 360SSM | Sound field mode is on the media player only (no standalone select) |
| `switch.bravia_quad_*_power` | Switch | Power | on/off | Disabled by default |
| `number.bravia_quad_*_volume` | Number | Main volume | 0–100 | Disabled by default |
| `number.bravia_quad_*_volume_step_interval` | Number | Delay between volume steps | 0–10000 ms | Disabled by default |
| `number.bravia_quad_*_rear_level` | Number | Rear speaker level | −10–10 | |
| `select.bravia_quad_*_bass_level` | Select | Bass level (no sub) | min, mid, max | Mutual exclusive with subwoofer level |
| `number.bravia_quad_*_subwoofer_level` | Number | Subwoofer level (with sub) | −10–10 | gRPC path `sound_setting.volume.subwoofer`; TCP uses `*_bass_level` number for the same job |
| `switch.bravia_quad_*_voice_enhancer` | Switch | Voice enhancer | on/off | |
| `switch.bravia_quad_*_voice_zoom` | Switch | Voice Zoom | on/off | Disabled by default |
| `number.bravia_quad_*_voice_zoom_level` | Number | Voice Zoom level | device range | Disabled by default |
| `switch.bravia_quad_*_sound_field` | Switch | Sound field on/off | on/off | Distinct from sound field **mode** on the media player |
| `switch.bravia_quad_*_night_mode` | Switch | Night mode | on/off | |
| `switch.bravia_quad_*_hdmi_cec` | Switch | HDMI CEC | on/off | |
| `switch.bravia_quad_*_advanced_auto_volume` | Switch | Auto Volume | on/off | Seeds / restore (not readable locally) |
| `select.bravia_quad_*_drc` | Select | Dynamic Range Compressor | auto, on, off | Seeds / restore |
| `select.bravia_quad_*_dual_mono` | Select | Dual mono | main, sub, main_sub | Disabled by default |
| `select.bravia_quad_*_imax_mode` | Select | IMAX Enhanced | auto, on, off | |
| `select.bravia_quad_*_bt_connection_quality` | Select | Bluetooth connection quality | prioritysound, priorityconnection | |
| `number.bravia_quad_*_av_sync` | Number | AV sync (HDMI) | device range | |
| `number.bravia_quad_*_tv_av_sync` | Number | AV sync (TV) | device range | |
| `switch.bravia_quad_*_audio_return_channel` | Switch | HDMI ARC (TV) / audio return | on/off | Seeds / restore; TCP keeps tri-state select |
| `select.bravia_quad_*_cec_power_off_sync` | Select | HDMI CEC power-off sync | auto, on, off | gRPC-only |
| `select.bravia_quad_*_display_brightness` | Select | Display brightness | bright, dark, off | Seeds / restore; gRPC-only |
| `switch.bravia_quad_*_dsee_ultimate` | Switch | DSEE Ultimate | on/off | Seeds / restore; gRPC-only |
| `select.bravia_quad_*_ssm_360_height` | Select | 360SSM height | high, mid, low | Seeds / restore; gRPC-only |
| `select.bravia_quad_*_center_speaker_mode` | Select | Center speaker mode | off, on | Disabled by default; gRPC-only; omitted when not in GetCapabilities |
| `switch.bravia_quad_*_dts_dialog_control` | Switch | DTS Dialog Control | on/off | Disabled by default; gRPC-only |
| `switch.bravia_quad_*_net_bt_standby` | Switch | Network/Bluetooth standby | on/off | |
| `switch.bravia_quad_*_auto_standby` | Switch | Auto standby | on/off | Disabled by default; Seeds / restore |
| `switch.bravia_quad_*_auto_update` | Switch | Auto update | on/off | Disabled by default; Seeds / restore |
| `switch.bravia_quad_*_external_control` | Switch | External control | on/off | Disabled by default; Seeds / restore |
| `select.bravia_quad_*_hdmi_standby_link` | Select | HDMI standby through | auto, on, off | Disabled by default; Seeds / restore |
| `button.bravia_quad_*_detect_subwoofer` | Button | Re-detect subwoofer | — | |
| `sensor.bravia_quad_*_device_name` | Sensor | Device name | — | |
| `sensor.bravia_quad_*_serial_number` | Sensor | Serial number | — | Disabled by default |
| `sensor.bravia_quad_*_ip_address` | Sensor | IP address | — | |
| `sensor.bravia_quad_*_mac_wired` | Sensor | MAC address (wired) | — | Omitted when not in GetCapabilities |
| `sensor.bravia_quad_*_timezone` | Sensor | Timezone | — | Disabled by default |
| `sensor.bravia_quad_*_raee_measured` | Sensor | Room calibration measured | — | Disabled by default; gRPC-only |
| `update.bravia_quad_*_firmware_update` | Update | Firmware update | — | HTTP |

### Seeds / unknown state

Paths marked **Seeds / restore** accept local gRPC writes but are not readable over local gRPC on current firmware. They may stay `unknown` until you enable **Seeds cloud reads** (`grpc_seeds_poll`), change the setting once, or HA restores prior state. See [seeds-cloud-states.md](seeds-cloud-states.md) and [sony-grpc-reference.md](sony-grpc-reference.md#notify-only-paths).

### Disabled by default

Enable under **Settings → Devices & Services → Entities** if needed. Unverified app settings (auto standby, auto update, external control, HDMI standby through) stay off until confirmed on your firmware; several other entities match TCP’s disabled defaults (power/volume companions, dual mono, voice zoom, etc.).

### Not in gRPC mode

Bluetooth pairing button, HDMI passthrough, temperature, and some network diagnostics remain TCP-only — see [grpc-tcp-mapping.md](grpc-tcp-mapping.md#parity-gaps).
