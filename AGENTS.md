# AGENTS.md

Instructions for AI coding agents working in this repository.

## Read these first

| File | What it gives you |
|---|---|
| [`docs/development/decisions.md`](docs/development/decisions.md) | **Why** the code is shaped this way. Read before changing anything structural. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Checks to run, version rules, `What not to change`. |
| [`TODO.md`](TODO.md) | What we actually want to work on. Not a mirror of any issue. |
| [`docs/development/review-brief.md`](docs/development/review-brief.md) | Review scope and settled decisions — do not re-raise them. |

If you change a recorded decision, update `decisions.md` **in the same commit**,
and update rule 1–7 below if it is an invariant with a regression test. A
decision that lives only in a diff is lost.

## Do not break these

**Rationale for each lives in
[`docs/development/decisions.md`](docs/development/decisions.md) — read it
before changing any of them**, because the obvious-looking "cleanup" usually
undoes a deliberate fix.

| # | Rule | Regression test |
|---|---|---|
| 1 | Write `entry.options` only through `settings.merge_options`. HA replaces the options mapping wholesale, so a bare dict literal silently deletes every setting you did not name. | yes — `test_options_flow.py`, `test_number.py::TestNumberPersistence` |
| 2 | `entry.data` is connection only (`api_key`, `base_url`). All settings live in `entry.options`, read via `settings.py`. | yes — `test_init.py::TestDataOptionsSeparation` |
| 3 | Do not remove the `RestoreEntity` read path in `number.py`. Prices set before v4.13.0 exist *only* in `restore_state`; the v5/v6 migrations seed the `0.0` default, so without the backfill those users' earnings silently read £0. It is now a **one-time** backfill, gated on `CONF_PRICE_RESTORE_PENDING` — see below. | yes — `test_number.py::TestPriceBackfillUpgrade`, `test_init.py::TestPriceBackfillMigration` |
| 4 | Assert API call counts, not sets. A set is invariant under duplication. | `test_coordinator.py::TestApiCallBudget` |
| 5 | Fetch summaries exactly once per `_async_update_data()`, after the turbine tier. Do not move the call into the initial `asyncio.gather` — `_next_slow_update` is advanced later, so an earlier call also sees the slow tier as due. | `TestApiCallBudget::test_summaries_are_fetched_exactly_once_per_update` |
| 6 | Do not split `coordinator.py` without call-budget coverage for whatever you move. | n/a — process rule |
| 7 | Keep `_parse_data()`'s dict guarantee. Callers depend on it. | `test_api.py::TestApiClient` |

### The price backfill is one-shot, and that is load-bearing

`RestoreEntity` is a *recovery mechanism*, not a source of truth. The v9
migration writes `CONF_PRICE_RESTORE_PENDING` (a **list** of the two price
option keys) into options for any pre-v9 entry. `_PriceBackfillMixin` then:

- **marker absent** → returns without reading `restore_state` at all. Options is
  authoritative, so a stale restore record cannot overwrite a price the user has
  since changed.
- **marker present** → reads `restore_state` once, persists the value, and drops
  its own key from the list. The marker is deleted once the list empties.

Two constraints that are easy to break:

1. **The marker must be a list, not a boolean.** Both number entities share one
   config entry. A shared boolean would let whichever set up first clear it, and
   the other price would never be recovered.
2. **`merge_options` cannot delete a key.** It is a spread
   (`{**existing, **incoming}`), so popping from the incoming dict leaves the
   existing value intact. The marker is removed from the *merged* result.

There is no "value is still the default, so backfill" shortcut: `0.0` is a
legitimate, meaningful value (`sensor.py` reports
`projection_basis=no_owner_price_zero` for it), so a value-equality guard would
retry the restore forever.

## Conventions

- Python 3.11+ compatible, `from __future__ import annotations` in every module.
- Line length 120 — but note the **nested
  `custom_components/kirkhill_wind/pyproject.toml` sets 88**, which is why
  `ruff check .` reports pre-existing E501s (20 lines exceed 88; none exceed
  120). CI runs `ruff check custom_components/ --config pyproject.toml` — the
  root config — and passes. `main` is protected: all three status checks
  (validate / test / min-ha) are required, so a direct push is declined with
  `GH006`. Push a branch and open a PR; checks run on the branch and gate the
  merge. Reconciling the two configs is tracked in `TODO.md`.
- Bump `VERSION` via `scripts/version_sync.py sync`, never by hand. It
  propagates to `manifest.json` and `pyproject.toml`.
- Any change under `custom_components/` needs a full Home Assistant restart.
  There is no code reload. **Never restart without the owner's explicit
  go-ahead** — that host is production.
- `python scripts/version_sync.py check` must pass before pushing.

## Verifying your work

Run the **actual test files**. A bespoke harness that reimplements a scenario
will pass while the real suite fails — that has happened, and only CI caught it.

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

CI is the gate: three jobs (`validate`, `test`, `min-ha`). If you cannot run
tests locally, say so plainly rather than reporting an unverified change as
working.

## Boundaries

- Frontend card JS (`custom_components/kirkhill_wind/frontend/`) cannot be
  tested by CI — no browser. Changes there need testing on a real instance.
- Bugs are tracked as GitHub issues; `TODO.md` is our own task list. Do not
  restate an issue's contents in the TODO.
- Never commit secrets. The API key is a runtime value, never a literal.
