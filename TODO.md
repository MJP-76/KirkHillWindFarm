# To-do list

Everything we plan to do lives here. Tick items off as you go and commit.
GitHub issue numbers are linked where they exist.

---

## Enhancements & API

### #54 — Expose unused response fields as sensors

Fields the coordinator already fetches but discards. No API changes needed.

- [x] `reading.complete` → binary_sensor (CONNECTIVITY) — whether all turbines are reporting
- [x] `reading.generated_at` → sensor (TIMESTAMP) — data freshness
- [x] `unknown_turbines` → sensor — count of turbines with no imported state
- [x] `latest_import_status` → sensor — import pipeline health (e.g. "completed")
- [x] `latest_rotor_speed_at` → per-turbine sensor (TIMESTAMP) — rotor data freshness (as `sampled_at` attribute on Rotor speed)
- [x] ~~Use full `/api/v1/wind-speed` time series~~ — dropped entirely; wind speed is already in the `current` endpoint summary. HA recorder handles historical charts. Saves 6 API calls/hour.

### #55 — API feature requests (require upstream API changes)

- [ ] Combined current + today summary endpoint — halve fast-tier round trips from 4 to 2 per poll (240→120 calls/hour)
- [ ] Per-turbine generation for intermediate ranges (7d, 30d, ytd, year) — `/api/v1/turbines` currently only supports `today` and `all`
- [ ] Structured curtailment reason in turbine state data (environmental / grid / maintenance / commercial)
- [ ] Confirm `/api/v1/generation` endpoint stability and build client support if stable
- [ ] Confirm `range=custom` with `from`/`to` stability and document rate limits
- [ ] Confirm unused response fields stability (see #54 above)
- [ ] Financial figures in the API response (negotiated price, member price, export price, price granularity, revenue figures)

### #37 — OAuth 2.1 PKCE authentication

- [ ] Add OAuth 2.1 Authorization Code flow with PKCE as alternative to manual API key entry (assigned: MJP-76)

### Dashboard & integration

- [ ] Rate limiting: expose `rate_limited` attribute on API status entity when API supports 429
- [x] ~~Remove the deprecated turbine map card~~ — JS file already deleted; OBSOLETE_CARD_KEYS entry stays to prune old dashboards.

## Code review backlog

- [x] Fetch the Open-Meteo forecast in parallel with timeframe summaries (was sequential; now runs as a parallel task when the slow tier is due, using cached turbine coordinates)
- [x] Investigate bare `except Exception` guards — both safe: dashboard load (YAML file, no API) and config flow (auth/connection errors caught first). No action needed.
- [x] `url_already_exists` string matching — replaced with `translation_key` attribute check (more robust than string matching against translated message)
- [x] ~~Split the ~700-line dashboard generation/merge logic out of `__init__.py`~~ — already done: `__init__.py` is 207 lines (setup/unload/listeners), `dashboard.py` is 519 lines (generation/merge/entity IDs).
- [ ] Add a platform-agnostic notification option (generic service/blueprint). Preference is WhatsApp, but design so other users can route to Telegram, Signal, or the HA Companion app

## Bugs — v4.13.4 ChatGPT review

All 18 findings verified against source. Two are real runtime defects.

### 🔴 Duplicate summary fetch — was shipping in stable v4.13.4

`_fetch_timeframe_summaries()` ran twice per `_async_update_data()`: once inside the
initial `asyncio.gather`, again after the turbine tier. The first result was unpacked
into `timeframe_summaries`/`timeframe_windows` and then immediately overwritten, so the
whole call was waste. `_next_slow_update` is only advanced *after* the second call, so
both invocations saw the slow tier as due.

- [x] Remove the redundant call from the initial gather
- [ ] Fix the test that let it through (see below)

Cost before the fix, at the default 60s scan interval: 2 wasted `get_summary` calls per
poll (~2,880/day), plus 14 more on each hourly slow poll (32 actual vs 18 intended,
because the first call populated `_immutable_year_summaries` and the second skipped only
the completed years).

### 🔴 No test can catch the duplicate — the assertion models the wrong property

`test_coordinator.py` asserts on a **set** of `(scope, range_value)` pairs, with a
comment saying this is deliberate ("so this cannot pass by coincidence"). A set is
invariant under duplication: it yields the same value for 2 calls as for 4, so the test
passes identically against the buggy and the correct implementation.

- [ ] Change the schedule test from set-based to count-aware assertions
- [ ] Add an API-call-budget regression test covering: normal poll, turbine-due poll,
      slow-tier poll, and completed-year caching

### 🟠 Malformed successful payload escapes as `AttributeError`

`_parse_data()` returned `body["data"]` with no type check, so a `{"data": []}` response
raised a bare `AttributeError` at `coordinator.py` (`payload.get("summary")`) and in
`get_turbines()` — where it fired *before* that method's own `isinstance` guard. Neither
is a `KirkHillApiError`, so the coordinator's stale-data and retry-backoff machinery never
engaged.

- [x] `_parse_data()` now validates the envelope *and* guarantees a `dict`, with distinct
      messages for a non-object body, a missing `data` key, and a non-object `data`
- [x] `get_turbines()` no longer needs its own guard — the dict guarantee covers it

### 🟠 RestoreEntity outranks the authoritative store — DO NOT simply remove it

`number.py` applies the RestoreEntity value over `entry.options` *unconditionally*, then
persists it back. Since v8 made options the authoritative source, that precedence is
inverted: a stale restore record can clobber the saved value.

**But removing RestoreEntity is a data-loss regression as proposed.** Up to v4.11.6,
`async_set_native_value` wrote nowhere — prices lived *only* in RestoreEntity. So anyone
who set a price before v4.13.0 has it in `restore_state` alone, and `options` holds only
the migration default of 50.0. Deleting the RestoreEntity read path would silently reset
those users to the default on upgrade.

Note: the `f570578` RestoreEntity→options persist fix is doing more than its release note
claimed. It is the **only** path carrying pre-v4.12 prices into options, not just a
desync fix.

- [ ] Make RestoreEntity a **one-time backfill** rather than a per-start override, so it
      cannot outrank options in steady state
- [ ] Only then consider dropping it, and only in a release users reach from a version
      that already ran the backfill
- [ ] Test a ≤v4.11.6 upgrade with a populated `restore_state` and empty options before
      touching this

### 🟢 "Completed years are immutable" — already mitigated, no action

The review flagged permanently caching completed years as risky for financial data. Not
applicable: `sensor.py` returns `None` for `alltime` and every `year_*` timeframe, so no
earnings value is ever derived from a cached year. Only generation kWh is exposed to a
backfill, which is a far weaker assumption to worry about. Revisit only if the API ever
gains a revenue field.

## Lint & coverage hygiene

From the v4.13.4 review. Explicitly **not** part of a correctness release — the reviewer
prescribed three separate PRs so config cleanup does not hide inside a bug fix.

- [ ] **PR A** — Decide the authoritative lint config. Root `pyproject.toml` sets
      `line-length = 120`; nested `custom_components/kirkhill_wind/pyproject.toml` sets
      `88`. Recommend deleting the nested one so there is a single project config.
- [ ] **PR B** — Fix the resulting lint debt (40 pre-existing E501s come from the nested
      88-char setting, not from new code)
- [ ] **PR C** — Enforce `ruff check .` in CI
- [ ] Enable `pytest-cov` in CI as **reporting only** (`--cov-report=term-missing`), no
      threshold yet. `pytest-cov` is in `requirements-dev.txt` but has never been invoked.
- [ ] Move the hardcoded `known_floors` HA→Python map out of `test_min_ha.py` into one
      documented place (currently `tests/test_min_ha.py:84`)

### The big refactor — remaining structural split of `__init__.py`

Review #62 §8 called `__init__.py` "an application controller" doing migration, setup,
services, frontend/JS registration, Lovelace dashboard create/merge/reset, payment
tracking, and entity-registry handling. The dashboard half was split out in v4.13.0
(`dashboard.py`); the rest is still there.

Target layout from the review:

```
custom_components/kirkhill_wind/
├── __init__.py        # setup/unload only
├── migration.py       # async_migrate_entry + version constant
├── services.py
├── device.py          # entity-registry helpers
├── dashboard/
│   ├── __init__.py
│   ├── builder.py     # build_dashboard_config
│   ├── merge.py       # merge_dashboard_config + card_match_key
│   └── constants.py   # OBSOLETE_* key sets
└── frontend/
```

Remaining work:

- [ ] Extract `async_migrate_entry` + `_CONFIG_ENTRY_VERSION` into `migration.py`
- [ ] Split `dashboard.py` (519 lines) into `dashboard/{builder,merge,constants}.py`
- [ ] Extract frontend/JS static-path registration into `frontend.py`
- [ ] Extract payment-tracking setup (`_async_setup_payment_tracking`) into its own module
- [ ] Re-export from `__init__.py` where tests import `_CONFIG_ENTRY_VERSION` / `async_migrate_entry`
- [ ] Tests must pass unchanged at each step — refactor only, no behaviour changes
- [ ] **Deferred:** split the coordinator (413 lines / 19.2 KB) into summary / turbine /
      forecast managers. Both reviews agree this is premature until the API-call-budget
      test exists, because that test is what makes the split safe rather than another
      behavioural change.

Note: do this as a pure structural change. Tests are already in place, so the "establish
tests before refactoring" precondition from review #62 is satisfied. The v4.13.4 review
reached the same conclusion independently.

## Housekeeping

- [x] Create a `SUPPORT` file (GitHub auto-features it in the repo file list)
- [x] Create a `CONTRIBUTING` file (GitHub auto-features it in the repo file list)
- [x] Submit to the official HACS default repository (PR #11379: https://github.com/hacs/default/pull/11379)

---

## Release history

Completed releases, newest first. Preserved for reference.

### v4.13.0 (pre-release, 2026-09-30)

- Config entry data/options separation, HA 2026.1.0 floor
- Fix RestoreEntity desync: persist restored prices to entry.options

### v4.11.7 (stable, 2026-09-29)

- Remove projected-annual-earnings from config flow and number entities
- Config migration v7: strip stale keys
- Fix past-year £ suppression for future `year_YYYY` frames

### v4.11.6 (stable, 2026-09-29)

- All-time generation = sum of per-year figures (2024 + 2025 + current YTD)
- Past-year figures kept as sensors only, removed from card panels
- Issues #57, #58 closed

### v4.11.5 (stable, 2026-09-29)

- Two price entities: Owner price (p/kWh) + Site/CfD price (£/MWh)
- Past-year generation rows (2025, 2024) from `range=YYYY` API
- All-time and past-year £ suppressed until CfD strike price confirmed
- Fix All time row slug mismatch (`gen-all-time` vs `gen-alltime`)
- Unified version strings via `scripts/version_sync.py`

### v4.11.4 (stable, 2026-09-29)

- Issue #57 portrait fixes: Capacity Factor label, Your Share styling

### v4.11.3 (stable, 2026-09-29)

- Fix MW chart y-axis trailing zeros (Site Power, Export Power)

### v4.11.2 (stable, 2026-09-28)

- Fix daily energy-chart totals (`state` vs `sum` recorder semantics)
- Eliminate trailing zeros on all chart y-axes

### v4.11.1 (stable, 2026-09-28)

- Same daily-statistics fix as v4.11.2 (parallel release)

### v4.11.0 (stable, 2026-09-28)

- Daily totals for energy charts on long timeframes
- Issue #57: duplicate "Since" removed, pill sizing fixes

### v4.9.0 (stable, 2026-09-27)

- Redesigned top chip row (Version, API, Turbine Status, Wind Speed)
- Turbine/API status pop-outs with history
- Card height locked, legend removed, tspan layout

### v4.8.81 (stable, 2026-09-27)

- Turbine map card deprecation banner
- API resilience hardening (shared aiohttp session, stale-data tolerance, gather turbine fetches, envelope guard, exponential backoff)

### v4.8.80 (stable, 2026-09-26)

- Turbines tab deleted, Google Maps link in turbine modal
- Negotiated CfD price number entity

### v4.8.79 (stable, 2026-09-26)

- OSM tile revert, £ earnings column in Generation & Capacity panels
- Finances tab retired and merged into SCADA

### v4.8.77 (stable, 2026-09-25)

- Deprecation banners on Finances/Turbines tabs
- History tab removed, Turbines tab trimmed, `graph_hours` option removed

### v4.8.74–v4.8.78

- Turbine Generation Today chart, API Status pill, map tile fallback
- SCADA bottom chrome row, themed chart tooltips, hourly stats

## Completed code reviews

- **Review #5 — API resilience hardening** (post-v4.8.80): all items done except Open-Meteo forecast parallelisation (carried above)
- **Review #1** — HACS default repository submission (PR #11379, done)
- **Reviews #2, #3, #4** — consolidated into the code review backlog above