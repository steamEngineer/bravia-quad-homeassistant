# What does this implement/fix?

<!-- Quick description and explanation of changes. -->

**Related issue (if applicable):**

- related issue <link to issue>

## Types of changes

<!--
Tick exactly one box. CI (.github/workflows/pr-labels.yaml) derives
the label from the ticked box and applies it automatically; release
drafter uses that label to slot this change into the changelog.
-->

- [ ] Bugfix (non-breaking change which fixes an issue) — `bugfix`
- [ ] New feature (non-breaking change which adds functionality) — `new-feature`
- [ ] Enhancement to an existing feature — `enhancement`
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected) — `breaking-change`
- [ ] Refactor (no behaviour change) — `refactor`
- [ ] Documentation only — `documentation`
- [ ] Maintenance / chore — `maintenance`
- [ ] CI / workflow change — `ci`
- [ ] Dependencies bump — `dependencies`
- [ ] Skip changelog — `skip-changelog`

## Checklist

- [ ] The code change is tested and works locally.
- [ ] `uv run pytest` passes, and tests have been added/updated under `tests/` where applicable.
- [ ] `uv run ty custom_components tests` passes.
- [ ] `./scripts/lint` passes (or `pre-commit run --all-files` if hooks are installed).
- [ ] User-facing strings updated in `strings.json` and `translations/en.json` when applicable.
- [ ] Live device smoke-tested via `./scripts/develop` when behaviour touches the Quad.

## Test plan

<!-- How was this tested? Include manual steps for device-facing changes. -->
