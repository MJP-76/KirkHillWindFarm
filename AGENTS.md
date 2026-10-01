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
| 3 | Do not remove the `RestoreEntity` read path in `number.py`. Prices set before v4.12 exist *only* in `restore_state`; removing the read path resets those users to the 50.0 default. Convert it to a one-time backfill first. | partial — persist-back covered, the <=v4.11.6 upgrade path is **not** |
| 4 | Assert API call counts, not sets. A set is invariant under duplication. | `test_coordinator.py::TestApiCallBudget` |
| 5 | Fetch summaries exactly once per `_async_update_data()`, after the turbine tier. Do not move the call into the initial `asyncio.gather` — `_next_slow_update` is advanced later, so an earlier call also sees the slow tier as due. | `TestApiCallBudget::test_summaries_are_fetched_exactly_once_per_update` |
| 6 | Do not split `coordinator.py` without call-budget coverage for whatever you move. | n/a — process rule |
| 7 | Keep `_parse_data()`'s dict guarantee. Callers depend on it. | `test_api.py::TestApiClient` |

Rule 3 is only partially covered: the persist-back path is tested, but nothing
covers a user upgrading from ≤v4.11.6, whose prices exist only in `restore_state`.
Write that test before touching the restore path — it is the one change here
that can silently cost a user real money.

## Conventions

- Python 3.11+ compatible, `from __future__ import annotations` in every module.
- Line length 120 — but note the **nested
  `custom_components/kirkhill_wind/pyproject.toml` sets 88**, which is why
  `ruff check .` reports pre-existing E501s. Reconciling the two is tracked in
  `TODO.md`; ruff is not yet a CI gate.
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
