# Documentation

Reference and guides for the [Bravia Theatre Home Assistant integration](../README.md).

## User guides

| Document | Description |
|----------|-------------|
| [configuration.md](configuration.md) | Setup, transport modes (TCP vs gRPC), migration |
| [grpc-setup.md](grpc-setup.md) | gRPC transport: Sony sign-in, options, Seeds cloud reads |
| [entities.md](entities.md) | Entity reference by transport |
| [troubleshooting.md](troubleshooting.md) | Connection, state sync, and gRPC issues |
| [Blueprints](../README.md#blueprints) | Source-based automation (import link in README) |

## Protocol reference

| Document | Description |
|----------|-------------|
| [tcp-protocol.md](tcp-protocol.md) | Legacy TCP port 33336 JSON commands |
| [sony-grpc-reference.md](sony-grpc-reference.md) | gRPC service, RPCs, session lifecycle |
| [grpc-auth-lifecycle.md](grpc-auth-lifecycle.md) | OAuth, session keys, and rolling auth_token lifecycles (living reference) |
| [grpc-tcp-mapping.md](grpc-tcp-mapping.md) | gRPC ↔ TCP entity mapping and parity gaps |
| [seeds-cloud-states.md](seeds-cloud-states.md) | Sony Seeds cloud reads for gRPC-unreadable settings (@mafredri) |
| [reverse-engineering-bravia-connect.md](reverse-engineering-bravia-connect.md) | How BRAVIA Connect gRPC control was reverse-engineered |

## Contributors

| Document | Description |
|----------|-------------|
| [development.md](development.md) | Dev environment, testing, CI, project layout |
| [AGENTS.md](../AGENTS.md) | Agent/PR conventions and script quick reference |
