# Troubleshooting

## Connection issues

If you encounter connection problems:

1. **Verify IP address**: Ensure the IP address is correct and the device is on the same network
2. **Check external control**: Verify that **External control** is enabled in the BRAVIA Connect app (see [README prerequisites](../README.md#prerequisites))
3. **Firewall (TCP)**: Ensure port 33336 is not blocked by your firewall
4. **Firewall (gRPC)**: Ensure port 55051 is not blocked by your firewall
5. **Test TCP connection**: For TCP transport, test manually using netcat — see [tcp-protocol.md](tcp-protocol.md#manual-connection-test)

## Entity states not updating

- Check the Home Assistant logs for any error messages
- **TCP**: Ensure the notification listener is running (check logs for "Starting notification listener")
- Try reloading the integration: **Settings** → **Devices & Services** → **Bravia Theatre** → **Reload**

## Volume or source shows default values

- The integration polls for initial values on startup
- If values don't update, check that the device is responding to get commands
- Notifications will update values in real-time when changes occur (TCP and gRPC where supported)

## gRPC-specific issues

Full gRPC setup walkthrough (including Chrome Network redirect copy): [grpc-setup.md](grpc-setup.md).

### Sony sign-in or session refresh failed

- Reconfigure the integration and complete Sony sign-in again
- Session keys expire after ~24 hours; the integration refreshes automatically when a refresh token is available — see [grpc-auth-lifecycle.md](grpc-auth-lifecycle.md)
- BRAVIA Connect may evict HA sessions; the reconnect loop re-seeds state after reconnect — see [sony-grpc-reference.md](sony-grpc-reference.md#session-lifecycle)

### Power on or exec fails after long standby (~1 hour)

Symptoms: entity stays `off`; logs show `Exec preflight full GetStates failed` / `INVALID_ARGUMENT` while gRPC still appears connected. Often follows playing → HA power off → ~1 h with no notify deltas.

Cause: rolling `session_random` / `auth_token` stale on an open notify session (cloud session keys usually still valid).

Fix (integration): automatic GetSessionRandom refresh on preflight failure; session restore + retry if exec still fails. Reload should not be required. Details: [grpc-auth-lifecycle.md](grpc-auth-lifecycle.md#idle-exec-failure-observed-1-h).

### Entities show `unknown` after setup

Some gRPC paths (including DRC and Auto Volume) are **writable** but **not readable** over local gRPC on current firmware. [@mafredri](https://github.com/mafredri) confirmed ([#16](https://github.com/steamEngineer/bravia-quad-homeassistant/issues/16)) that BRAVIA Connect reads these via Sony Seeds cloud API. Enable **Seeds cloud reads** in gRPC integration options (`grpc_seeds_poll`) — see [seeds-cloud-states.md](seeds-cloud-states.md). Without Seeds, HA uses restore or the last write (TCP seed only when Seeds is off on TCP-capable models).

### Wrong entity set or missing features

Transport is chosen at setup and cannot be switched in place. Remove and re-add the integration to change between TCP and gRPC — see [configuration.md](configuration.md#transport-modes).

### Missing TCP-only features on gRPC

Bluetooth pairing button, HDMI passthrough, temperature, and some network diagnostics are TCP-only or have no confirmed gRPC path — see [grpc-tcp-mapping.md](grpc-tcp-mapping.md#parity-gaps).
