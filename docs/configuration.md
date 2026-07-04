# Configuration

## Auto-discovery

The integration supports automatic discovery of Bravia Theatre devices on your local network using mDNS/zeroconf. When you add the integration, Home Assistant will automatically detect any Bravia Theatre devices and prompt you to configure them.

**If your device is not automatically discovered**, you can add it manually by:

1. Selecting "Bravia Theatre" from the integration list
2. Choosing "Configure" or "Submit" when prompted
3. Entering the device's IP address manually
4. Optionally providing a friendly name (defaults to "Bravia Theatre")

## Manual configuration

During setup, you will be prompted to provide:

- **IP Address**: The IP address of your Bravia Theatre device (required if not auto-discovered)
- **Transport**: **gRPC** (recommended, **EXPERIMENTAL** — BRAVIA Connect via Sony sign-in) or **TCP** (legacy IP control, no sign-in)
- **Sony sign-in** (gRPC only): Complete the in-integration OAuth flow when prompted (session keys refresh automatically when possible)
- **Name** (optional): A friendly name for the device (defaults to "Bravia Theatre")

## Transport modes

| Mode | Connection | Highlights |
|------|------------|------------|
| **gRPC** (recommended, **EXPERIMENTAL**) | gRPC port 55051 + HTTP | BRAVIA Connect control plane: live notify, now-playing metadata, play/pause/next on streaming inputs, sound field mode, DSEE Ultimate, 360SSM height, center speaker, DTS Dialog Control, subwoofer level (~40 entities). Expect parity gaps and breaking changes |
| **TCP** (legacy) | TCP port 33336 + HTTP | No Sony sign-in; fewer streaming and sound features (~44 entities). Extras include Bluetooth pairing button, HDMI passthrough, temperature, and network diagnostics |

See [grpc-tcp-mapping.md](grpc-tcp-mapping.md#parity-gaps) for the full parity gap list and entity mapping table.

HTTP is always used for firmware update and network diagnostic sensors regardless of transport. Changing transport requires removing and re-adding the integration (entity set differs per mode).

Legacy entries with **Enable gRPC state sync** in options are migrated automatically to gRPC transport on reload.

## Connection requirements

The integration will automatically test the connection during setup.

**TCP mode** — ensure:

- External control is enabled on your Bravia Theatre device (see [README prerequisites](../README.md#prerequisites))
- The device is accessible on your network
- Port 33336 is not blocked by a firewall

**gRPC mode** — ensure:

- External control is enabled
- Port 55051 is not blocked by a firewall
- You complete Sony sign-in during setup (session keys refresh automatically when a refresh token is available)

See [troubleshooting.md](troubleshooting.md) for connection debugging.
