# Entities

The integration creates entities under your Bravia Theatre device. The entity set depends on the transport chosen at setup — see [configuration.md](configuration.md#transport-modes).

## TCP transport (baseline)

The table below lists the core entities shared with or superseded by gRPC mode. TCP mode adds diagnostic extras (Bluetooth pairing button, HDMI passthrough, temperature, network sensors) not available over gRPC.

| Entity | Type | Description | Range/Options |
|--------|------|-------------|---------------|
| `media_player.bravia_quad_*` | Media player | Power, volume, mute, source | Sources: TV (eARC), HDMI In, Spotify, Bluetooth, AirPlay |
| `switch.bravia_quad_*_power` | Switch | Control power on/off (Configuration; use media player for playback) | on/off |
| `number.bravia_quad_*_volume` | Number | Control main volume | 0-100 |
| `number.bravia_quad_*_volume_step_interval` | Number | Delay between volume steps | 0-10000 ms (1ms steps) |
| `number.bravia_quad_*_rear_level` | Number | Control rear speaker level | -10-10 |
| `number.bravia_quad_*_bass_level` | Number | Control bass level (with subwoofer) | -10-10 |
| `select.bravia_quad_*_bass_level` | Select | Control bass level (without subwoofer) | MIN, MID, MAX |
| `switch.bravia_quad_*_voice_enhancer` | Switch | Toggle voice enhancer | on/off |
| `switch.bravia_quad_*_sound_field` | Switch | Toggle sound field processing | on/off |
| `switch.bravia_quad_*_night_mode` | Switch | Toggle night mode | on/off |
| `switch.bravia_quad_*_hdmi_cec` | Switch | Toggle HDMI CEC | on/off |
| `switch.bravia_quad_*_auto_standby` | Switch | Toggle auto standby | on/off |
| `select.bravia_quad_*_drc` | Select | Dynamic Range Compressor (DRC) | Auto, On, Off |
| `switch.bravia_quad_*_advanced_auto_volume` | Switch | Auto Volume | on/off |
| `button.bravia_quad_*_detect_subwoofer` | Button | Re-detect subwoofer (diagnostic) | - |
| `button.bravia_quad_*_bluetooth_pairing` | Button | Trigger Bluetooth pairing mode (TCP only) | - |

*Note: `*` represents your device's unique entry ID.*

*Note: Only one bass level entity will be created based on whether a subwoofer is detected.*

## gRPC transport

gRPC mode exposes ~40 mapped entities via [grpc-tcp-mapping.md](grpc-tcp-mapping.md), including:

- **Media player** — power, volume, mute, source, sound field mode (`sound_setting.sound_effect`), now-playing metadata, and play/pause/next/previous on streaming inputs
- **gRPC-only controls** — CEC power-off sync, DSEE Ultimate, 360SSM height, center speaker, DTS Dialog Control, subwoofer level (with sub), dual mono, and more

Input source and sound field mode are on the media player only (no standalone select entities). Some settings may show `unknown` until changed or restored — see [sony-grpc-reference.md](sony-grpc-reference.md#notify-only-paths).
