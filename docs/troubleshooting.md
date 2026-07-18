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

With Seeds on, app-side changes refresh via a debounced Seeds GET after a `playback_control.no_audio` notify. If nothing is playing, a second app change may not trigger another refresh until playback resumes — see [seeds-cloud-states.md](seeds-cloud-states.md#operational-behavior).

### Missing HTTP diagnostics or firmware update

Internet, IPv6, Wi‑Fi signal, MAC, and firmware-update entities are created only when the management FCGI probe on `:54545` succeeds. Some gRPC-only models skip that endpoint entirely — expected, not a failed setup. See [configuration.md](configuration.md#transport-modes) and [entities.md](entities.md#http-management-both-transports).

### Stale or extra entities after upgrade

Capability-gated and HTTP probe-gated entities that this run will not recreate are removed from the entity registry on setup. Reload the integration if you still see leftovers from an older build.

### Second Theatre treated as already configured

Zeroconf rediscovery matches by host or MAC. A second Theatre should prompt a new config entry; if an older build linked it to the first serial, remove the bad entry and re-add, or update to a build that includes host/MAC matching — see [configuration.md](configuration.md#auto-discovery).

### Rapid power toggles ignored

gRPC media-player power on/off is rate-limited to once every 5 seconds so rapid toggles during a power transition are dropped. Wait a few seconds and try again.

### Wrong entity set or missing features

Transport is chosen at setup and cannot be switched in place. Remove and re-add the integration to change between TCP and gRPC — see [configuration.md](configuration.md#transport-modes). Mapped gRPC entities also depend on `GetCapabilities` for your model — see [entities.md](entities.md#grpc-transport).

### Missing TCP-only features on gRPC

Bluetooth pairing button, HDMI passthrough, temperature, and some network diagnostics are TCP-only or have no confirmed gRPC path — see [grpc-tcp-mapping.md](grpc-tcp-mapping.md#parity-gaps).
