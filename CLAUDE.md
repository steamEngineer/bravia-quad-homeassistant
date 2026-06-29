# CLAUDE.md

## Behaviour

- Do not post GitHub PR or issue comments without explicit user consent.

## Branching and PRs

- All PRs target `main`.
- Fill in [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md); tick exactly one change type (the **PR Labels** workflow applies and verifies the matching label automatically).
- PR title: functional description of the change. Do not use conventional commit prefixes such as `feat:`, `fix:`, or `chore:` — labels categorize PRs, not the title.
- PR body: include a test plan; device-facing changes should note live Quad smoke testing when applicable.

## Development

- `./scripts/setup` — dependencies and pre-commit hooks
- `uv run pytest` — test suite
- `uv run ty custom_components tests` — type checking
- `./scripts/lint` — Ruff lint and format
- `./scripts/develop` — local Home Assistant (http://localhost:8123)

Run `./scripts/lint` and `uv run pytest` after code changes.

## Code standards

Integration patterns, entity conventions, and review guidance: [`.github/copilot-instructions.md`](.github/copilot-instructions.md).
