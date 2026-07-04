# Bravia gRPC standalone tools

Optional CLI helpers for Sony Seeds OAuth and session key extraction. The Home Assistant integration performs the same OAuth flow during setup — use this script only for local debugging.

## Home Assistant integration

Setup chooses **TCP** (default, full entity set) or **gRPC** (experimental subset) at config time — not both. See [docs/configuration.md](../../docs/configuration.md#transport-modes) for transport details.

| Doc | Purpose |
|-----|---------|
| [sony-grpc-reference.md](../../docs/sony-grpc-reference.md) | RPC + credential reference |
| [grpc-tcp-mapping.md](../../docs/grpc-tcp-mapping.md) | Entity mapping table |

## CLI session keys

Run from repo root:

```bash
# OAuth → write keys to a local file (never commit the output)
uv run python scripts/grpc/get_session_keys.py -o /tmp/session_keys.json
```

The script opens a browser for Sony sign-in, lists your Bravia devices, and writes `device_id`, `session_key`, `hmac_key`, and OAuth tokens to the output file. See [`session_keys_example.json`](session_keys_example.json) for the expected shape (keys only, no live credentials).
