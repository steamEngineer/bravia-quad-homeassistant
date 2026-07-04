# Bravia Theatre Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-green.svg)](https://github.com/custom-components/hacs)
![GitHub Downloads](https://img.shields.io/github/downloads/steamEngineer/bravia-quad-homeassistant/total)
![GitHub Release](https://img.shields.io/github/v/release/steamEngineer/bravia-quad-homeassistant)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Home Assistant custom integration for Sony Bravia Theatre home theater systems. Choose **gRPC** (experimental, BRAVIA Connect control plane) or **TCP** (legacy IP control, no Sony sign-in) at setup.

_See [device compatibility](docs/device-compatibility.md) for supported models._

> **Legal and ethical note**
>
> This work was done for **interoperability** — making hardware I own talk to software I run — which is the purpose most explicitly protected for reverse engineering (e.g. the interoperability exemptions under 17 U.S.C. § 1201(f) in the US and Article 6 of the EU Software Directive). It was all done on **my own HT-A9M2, on my own LAN, with my own Sony account and my own credentials.** Nothing here touched anyone else's device, account, or network.
>
> What this project contains and doesn't:
>
> - **No Sony source code, binaries, or assets** were copied, decompiled for redistribution, or shipped. The integration is a clean-room reimplementation of the *wire protocol* — the observable bytes on the network — not of Sony's software.
> - **No secrets are published.** The `client_id` and `x-api-key` values that appear here are non-secret identifiers already sent by the app on every request; they are not account credentials. Session keys, HMAC keys, OAuth tokens, and device IDs are per-user and per-device, are never committed, and are gitignored (see [reverse-engineering-bravia-connect.md](docs/reverse-engineering-bravia-connect.md) for redaction notes).
> - **No Sony service was attacked or overloaded.** Traffic capture was passive observation of my own sessions; the only requests made to Sony's cloud were the same OAuth/session-key calls the official app makes, at human scale.
> - **Credentials belong to the user.** The integration authenticates as *you*, with keys *you* obtain by signing into *your* Sony account — it stores no shared or embedded credential.
>
> Practical caveats: this is an **unofficial** integration with **no affiliation with or endorsement by Sony**. It targets one model on one firmware (`001.454`); Sony can change or break the protocol at any time, and firmware updates may disable it. Trademarks (Sony, BRAVIA) belong to their owners and are used here only to identify the device. **Use at your own risk** — there is no warranty, and you are responsible for complying with the terms of service and laws that apply in your own jurisdiction. Nothing in this document is legal advice.

<details>
<summary>View Device Page Screenshot</summary>

<img src="assets/pictures/bravia_quad_device_page.png" alt="Bravia Quad Device Page in Home Assistant" width="500">

</details>

## Features

- **Auto-discovery** via mDNS/zeroconf — no manual IP required
- **Power, volume, mute, and source** control via media player and companion entities
- **Rear and bass level** — bass adapts automatically (slider with subwoofer, MIN/MID/MAX without)
- **Audio settings** — voice enhancer, sound field, night mode, DRC, auto volume, HDMI CEC, auto standby
- **Real-time updates** from the device where the transport supports notify/push
- **gRPC extras (experimental)** — now-playing metadata, sound field mode select, play/pause/next on Spotify/Bluetooth/AirPlay, DSEE Ultimate, 360SSM height, and more (~40 entities)
- **Single device** — all entities nested under one Bravia Theatre device in Home Assistant

Full entity list: [docs/entities.md](docs/entities.md)

## Prerequisites

Before setup, enable **External control** on your Bravia device:

1. Open the **BRAVIA Connect** app
2. Go to **Settings** → **Network settings**
3. Enable **External control**

> Without this setting, the integration cannot communicate with your device.

## Installation

### HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Go to HACS → Integrations
3. Search for "Bravia Theatre" and install it
4. Restart Home Assistant

### Manual Installation

1. Copy the `bravia_quad` folder to `<config>/custom_components/bravia_quad/`
2. Restart Home Assistant
3. Go to **Settings** → **Devices & Services** → **Add Integration**
4. Search for "Bravia Theatre" and follow the setup wizard

## Configuration

The integration discovers Bravia Theatre devices automatically. If yours is not found, add it manually with the device IP address.

During setup you choose a **transport**:

| Mode | Connection | Summary |
|------|------------|---------|
| **gRPC** (recommended, **EXPERIMENTAL**) | Port 55051 + HTTP | BRAVIA Connect plane; Sony sign-in; streaming controls and extended sound settings |
| **TCP** (legacy) | Port 33336 + HTTP | No sign-in; full diagnostic extras (Bluetooth pairing, temperature, network sensors) |

gRPC mode prompts for Sony sign-in (OAuth). Session keys refresh automatically when possible.

Details, parity gaps, and migration: [docs/configuration.md](docs/configuration.md#transport-modes)

## Blueprints

Automate settings (**Voice Enhancer**, **Auto Volume**, **Sound Field**, **Night Mode**, **Volume**, **Rear Level**) per input source.

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FsteamEngineer%2Fbravia-quad-homeassistant%2Fblob%2Fmain%2Fblueprints%2Fsource_based_config.yaml)

**Manual import:** Settings → Automations & Scenes → Blueprints → Import Blueprint → paste:

`https://github.com/steamEngineer/bravia-quad-homeassistant/blob/main/blueprints/source_based_config.yaml`

## Documentation

| Topic | Document |
|-------|----------|
| **All docs** | [docs/README.md](docs/README.md) |
| Setup & transport | [docs/configuration.md](docs/configuration.md) |
| Entities | [docs/entities.md](docs/entities.md) |
| Device compatibility | [docs/device-compatibility.md](docs/device-compatibility.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| TCP protocol | [docs/tcp-protocol.md](docs/tcp-protocol.md) |
| gRPC reference | [docs/sony-grpc-reference.md](docs/sony-grpc-reference.md) |
| gRPC entity mapping | [docs/grpc-tcp-mapping.md](docs/grpc-tcp-mapping.md) |
| Reverse-engineering story | [docs/reverse-engineering-bravia-connect.md](docs/reverse-engineering-bravia-connect.md) |
| Development | [docs/development.md](docs/development.md) |

## Contributing

Contributions welcome! Open a pull request against `main` and complete [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md). See [docs/development.md](docs/development.md) for setup and testing.

## License

This integration is provided as-is under the MIT License.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Made with ❤️ for the Home Assistant community**
