# Contributing

Thanks for your interest in contributing to the Kirk Hill Wind Farm integration.

## Getting started

1. Fork and clone the repository.
2. Create a branch from `main` for your change.
3. Set up a development environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install homeassistant
   pip install -r requirements-dev.txt
   ```

## Running checks locally

```bash
# Tests
pytest tests/ -v --tb=short

# Linting (ruff, line-length 120)
ruff check custom_components/ --config pyproject.toml

# Version sync check (VERSION, manifest.json, pyproject.toml must agree)
python scripts/version_sync.py check
```

## What CI checks

Every push and pull request runs:

| Job | What it checks |
|---|---|
| **validate** | Python compile, import against installed HA, manifest JSON, version sync |
| **test** | `pytest tests/` against the latest Home Assistant |
| **min-ha** | Import and tests against the minimum supported Home Assistant version declared in `hacs.json` |
| **HACS Validation** | HACS structural requirements for custom integrations |
| **Hassfest** | Home Assistant's own integration validator |
| **ruff** | Linting (E, F, I, W rules, line-length 120) |

## Commit messages

Use a short prefix to describe the area of change:

- `Fix ...` — bug fix
- `Docs ...` — documentation only
- `Add ...` — new feature or sensor
- `Refactor ...` — restructuring without behaviour change
- `Test ...` — test-only change

Keep the subject line under 72 characters. Reference issue numbers where
relevant (e.g. `Fix #54: expose reading.complete as binary sensor`).

## Versioning

The single source of truth for the version is the `VERSION` file. Before
committing a version bump, run:

```bash
python scripts/version_sync.py sync
```

This updates `manifest.json` and `pyproject.toml` to match. CI will fail if
they drift.

## Pull requests

- Keep PRs focused on one change.
- Include tests for new sensors or changed behaviour.
- Update the docs (`docs/`) if the change affects what users see or configure.
- Update `CHANGELOG.md` for user-facing changes.
- **If you change a decision recorded in `docs/development/decisions.md`, update
  that file in the same commit** — and if it is a rule an agent could break
  (an invariant with a regression test), update the matching bullet in
  `AGENTS.md` too. A decision that lives only in a diff is lost. That is the
  whole mechanism; there is no other guard against drift.
- Bump `VERSION` with `python scripts/version_sync.py sync`, never by hand.

## Code style

- Python 3.11+ compatible (the minimum supported HA version).
- Use `from __future__ import annotations` in all modules.
- Line length: 120 characters (ruff and black).
- Type hints where practical.

## What not to change

- The `hacs.json` `homeassistant` field without updating the `min-ha` CI job
  and `version_sync.py` minimum version logic.
- The bundled frontend cards (`dashboard.py`, card JS) without testing on a
  real Home Assistant instance — CI does not run a browser.