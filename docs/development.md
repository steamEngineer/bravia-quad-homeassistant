# Development

See also [AGENTS.md](../AGENTS.md) for PR conventions and the canonical script quick reference.

## Native host development (recommended for Quad LAN)

On WSL or Linux with the device on your LAN, run Home Assistant directly on the host:

```bash
./scripts/setup      # dependencies + pre-commit hooks
./scripts/develop    # Home Assistant at http://localhost:8123
```

Native `./scripts/develop` has direct access to the Quad on TCP port 33336 and gRPC port 55051 (required for live device debugging and Sony OAuth).

## DevContainer

You can also develop using the included DevContainer with Visual Studio Code:

1. Install [Visual Studio Code](https://code.visualstudio.com/) and the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Clone this repository
3. Open in VS Code and **Reopen in Container**
4. Run `./scripts/develop` inside the container

### DevContainer network modes

The devcontainer supports two network modes (switch via VS Code tasks):

| Mode | Use case |
|------|----------|
| **Bridge** (default) | General development; ports forwarded to host |
| **Host** | **Required for mDNS/zeroconf discovery** — container receives multicast DNS from your LAN |

mDNS/zeroconf relies on Layer 2 multicast traffic that bridge networking isolates from the container.

**Switching network modes:**

1. Command Palette → **Tasks: Run Task**
2. Select **Devcontainer: Set Host Network Mode** or **Devcontainer: Set Bridge Network Mode**
3. Rebuild: Command Palette → **Dev Containers: Rebuild Container**

> **Docker Desktop users:** Host networking may require enabling **Enable host networking** under Settings → Resources → Network (Docker Desktop 4.34+, Linux containers only). See [Docker host networking docs](https://docs.docker.com/engine/network/drivers/host/#docker-desktop).

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/setup` | Sets up development environment with uv (installs dependencies + prek hooks) |
| `scripts/develop` | Starts Home Assistant with the integration in debug mode |
| `scripts/lint` | Runs Ruff to format and lint the code |

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
./scripts/setup

# Or manually
uv sync --dev
uv run prek install --overwrite --install-hooks
```

## Project structure

```
custom_components/bravia_quad/
├── __init__.py                 # Integration setup, platform forwarding
├── config_flow.py              # Config flow (TCP/gRPC transport, OAuth)
├── transport.py                # Transport selection
├── bravia_quad_client.py       # TCP client
├── bravia_grpc_client.py       # gRPC client (notify, GetStates, ExecCommand)
├── bravia_http_client.py       # HTTP (firmware, diagnostics)
├── grpc_mapping.py             # gRPC path → entity mapping table
├── grpc_mapped_entities.py     # Generic gRPC entity factories
├── grpc_media_player.py        # gRPC media player
├── grpc_tcp_seed.py            # TCP seed for notify-only gRPC paths
├── media_player.py             # TCP media player
├── switch.py / number.py / select.py / sensor.py / button.py / update.py
├── grpc/                       # Wire encoders, proto, credentials
└── manifest.json
tests/                          # pytest suite
scripts/                        # Dev and optional gRPC CLI tools
```

## Code quality

[Ruff](https://docs.astral.sh/ruff/) for linting and formatting (Home Assistant standards). Python 3.14.2+.

```bash
./scripts/lint   # Ruff + ty (custom_components/bravia_quad)
```

## Testing

Tests run in parallel by default (`pytest-xdist`); a full run takes roughly 10–15 seconds.

```bash
uv run pytest                                    # all tests (parallel)
uv run pytest tests/test_config_flow.py          # single file
uv run pytest tests/test_select.py::test_input_select_spotify
uv run pytest --lf                               # re-run failures
uv run pytest -n0                                # serial (debugging)
uv run pytest -v
uv run pytest --cov=custom_components/bravia_quad
```

For manual TCP connection testing, see [tcp-protocol.md](tcp-protocol.md#manual-connection-test).

## CI/CD

GitHub Actions on every pull request:

- **Hassfest** — manifest and HA standards validation
- **Forbidden paths** — blocks private/local artifacts and credential-shaped content
- **Lint** — Ruff and Ty (`custom_components/bravia_quad`)
- **Tests** — pytest

Release workflow validates version format, updates `pyproject.toml` and `manifest.json`, tags, and publishes GitHub releases.

Dependencies are kept up to date via [Renovate](https://docs.renovatebot.com/) (GitHub Actions, Python packages).

## Contributing

Open a pull request against `main` and complete [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md).

1. **Code style**: Follow existing patterns; use Ruff
2. **Testing**: Run `./scripts/lint` and `uv run pytest` before submitting
3. **Pull requests**: Tick exactly one change type; ensure CI passes; update docs if needed
4. **Issues**: Open an issue first for bugs or feature requests when appropriate

Integration patterns and review guidance: [`.github/copilot-instructions.md`](../.github/copilot-instructions.md).

## Private local artifacts

Some paths are **local-only** and must never be committed or pushed. See [`.gitignore`](../.gitignore) for the canonical denylist; `scripts/forbid_private_commit.sh` also blocks gitignored `.cache/` trees that may not be reported correctly by `git check-ignore` in every layout.

Tracked dev helpers include `scripts/check_connection.py`, `scripts/grpc/get_session_keys.py`, and `scripts/grpc/session_keys_example.json` (placeholders only — never commit `scripts/grpc/session_keys.json`).

Extended gRPC wire-capture tests optionally read local capture fixtures under gitignored `.cache/`; they skip when captures are absent (CI does not require them).

### How protection works

1. **`.gitignore`** — blocks casual `git add` of private paths.
2. **Pre-commit / pre-push hooks** — installed by `./scripts/setup`; reject staged or pushed forbidden paths, including `git add -f` on ignored files. Credential-shaped values in `scripts/grpc/*.json` diffs are also rejected.
3. **CI** — the Forbidden paths job in Validation runs the same script on every PR and push to `main`.

If the hook blocks your commit, unstage with `git reset HEAD -- <path>`. Never use `git add -f` on ignored private paths.
