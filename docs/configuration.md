# Configuration

## Auto-discovery

The integration supports automatic discovery of Bravia Theatre devices on your local network using mDNS/zeroconf. When you add the integration, Home Assistant will automatically detect any Bravia Theatre devices and prompt you to configure them. Rediscovery updates an existing config entry only when the host or MAC matches — multiple Theatres on the same network each get their own entry.

Wi‑Fi-only models (no wired MAC in capabilities) use the wireless MAC for device identity and network connections.

**If your device is not automatically discovered**, you can add it manually by:

1. Selecting "Bravia Theatre" from the integration list
2. Choosing "Configure" or "Submit" when prompted
3. Entering the device's IP address manually
4. Optionally providing a friendly name (defaults to "Bravia Theatre")

## Manual configuration

During setup, you will be prompted to provide:

- **IP Address**: The IP address of your Bravia Theatre device (required if not auto-discovered)
- **Transport**: **gRPC** (recommended — BRAVIA Connect via Sony sign-in) or **TCP** (legacy IP control, no sign-in)
- **Sony sign-in** (gRPC only): Complete the in-integration OAuth flow when prompted (session keys refresh automatically when possible)
- **Name** (optional): A friendly name for the device (defaults to "Bravia Theatre")

## Transport modes

| Mode | Connection | Highlights |
|------|------------|------------|
| **gRPC** (recommended) | gRPC port 55051 + HTTP | BRAVIA Connect control plane: live notify, now-playing metadata, play/pause/next on streaming inputs, sound field mode, DSEE Ultimate, 360SSM height, center speaker, DTS Dialog Control, subwoofer level. See [entities.md](entities.md) and [grpc-tcp-mapping.md](grpc-tcp-mapping.md) |
| **TCP** (legacy) | TCP port 33336 + HTTP | No Sony sign-in; fewer streaming and sound features. Extras include Bluetooth pairing button, HDMI passthrough, temperature, and network diagnostics |

> **Beta Feature:** gRPC is the recommended transport and still evolving — expect parity gaps vs TCP and occasional changes across releases or firmware.

**gRPC setup walkthrough** (Sony sign-in, Chrome Network redirect, Seeds options): [grpc-setup.md](grpc-setup.md).

See [grpc-tcp-mapping.md](grpc-tcp-mapping.md#parity-gaps) for the full parity gap list and entity mapping table.

HTTP (`:54545`) is used for firmware update and network diagnostic sensors when the management FCGI endpoint on that port responds. Devices without that endpoint (for example some gRPC-only models) skip those entities. Changing transport requires removing and re-adding the integration (entity set differs per mode).

Legacy entries with **Enable gRPC state sync** in options are migrated automatically to gRPC transport on reload.

## Options (gRPC transport)

After setup, open the integration → **Configure** to change gRPC options:

| Option | Default | Description |
|--------|---------|-------------|
| **Verbose gRPC debug logging** (`grpc_debug`) | off | Extra debug logs for the local gRPC session |
| **Read notify-only settings from Sony Seeds cloud** (`grpc_seeds_poll`) | off | Opt-in cloud reads for settings that local gRPC does not return (same Sony API BRAVIA Connect uses; credit [@mafredri](https://github.com/mafredri)). See [seeds-cloud-states.md](seeds-cloud-states.md). |

TCP transport has no options step.

## Connection requirements

The integration will automatically test the connection during setup.

**TCP mode** — ensure:

- External control is enabled on your Bravia Theatre device (see [README prerequisites](../README.md#prerequisites))
- The device is accessible on your network
- Port 33336 is not blocked by a firewall

**gRPC mode** — ensure:

- Port 55051 is not blocked by a firewall
- You complete Sony sign-in during setup (session keys refresh automatically when a refresh token is available)

External control is checked and enabled automatically during gRPC setup when possible — see [grpc-setup.md](grpc-setup.md).

See [troubleshooting.md](troubleshooting.md) for connection debugging.

## Removal

To remove the integration and its entities:

1. Go to **Settings** → **Devices & Services**
2. Select **Bravia Theatre**
3. Open the three-dot menu on the config entry → **Delete**

This removes the config entry and associated entities. Automations that reference those entity IDs will need updating. To switch between gRPC and TCP, remove the entry and add the integration again (entity sets differ per transport).
