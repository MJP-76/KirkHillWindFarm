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
- [ ] `co2_avoided_kg` → sensors (owner + site) — WEIGHT, kg, windowed `measurement`, fed
      from the timeframe summaries we already fetch (no new API calls — `/api/v1/carbon-avoided`
      duplicates the same figure). Must carry the coverage attributes
      (`co2_avoided_coverage_percent`, `_matched/_expected_intervals`, `_complete`,
      `assumed_export_factor`, `latest_carbon_intensity_at`) so it reads "indicative, 98%
      coverage" rather than a bare number. Expose owner + site only (today/YTD), not the full
      timeframe matrix. Reference: `njp970/ha_kirkhill` `co2_avoided_owner`/`co2_avoided_site`.
- [ ] Site `capacity_watts` → sensor (POWER, W, DIAGNOSTIC, disabled by default) — the 18.8 MW
      figure arrives in every `/api/v1/current` payload; only *owner* capacity surfaces today,
      as an attribute of Member savings value.

### #55 — API feature requests (require upstream API changes)

- [ ] Combined current + today summary endpoint — halve fast-tier round trips from 4 to 2 per poll (240→120 calls/hour)
- [ ] Per-turbine generation for intermediate ranges (7d, 30d, ytd, year) — `/api/v1/turbines` currently only supports `today` and `all`
- [ ] Structured curtailment reason in turbine state data (environmental / grid / maintenance / commercial)
- [ ] Confirm `/api/v1/generation` endpoint stability and build client support if stable
- [ ] Confirm `range=custom` with `from`/`to` stability and document rate limits
- [ ] Confirm unused response fields stability (see #54 above)
- [ ] **Financial figures in the API response** — the target design. See
      [Target design: prices owned by the API](#target-design-prices-owned-by-the-api)
      below, and [#55 §6](https://github.com/MJP-76/KirkHillWindFarm/issues/55) for the
      upstream request. **Awaiting the board** (asked 2026-10-01).

### Target design: prices owned by the API

**The goal.** CfD strike rate, sell/export price, and owner price all come from the API
rather than being user-entered. The integration stops *asserting* financial figures and
starts *reporting* them. Board has been asked; not yet answered.

**Why this is the right direction, not just a data source.** It removes three things at
once:

- the `suppressed_no_historical_price` branch at `sensor.py:487`, which currently returns
  `None` for `alltime` and every `year_*` timeframe because no per-year price exists
- both `number` price entities
- the whole class of bug where `entry.options` and `restore_state` disagree about money —
  the class v4.13.6 just finished cleaning up

The coordinator would read prices rather than assert them, and earnings would need zero
user configuration.

**Ask the API for effective-dated ranges, not year keys.** A CfD strike rate does not
normally change on 1 January. If it changes on 1 July, a `2025: 85.0` entry is wrong for
half that year, and the failure is invisible — plausible numbers that are quietly wrong.
Request `{effective_from, effective_to, rate}`, which handles renegotiation, partial years,
and a contract that started mid-year. Year-keyed data is easier to ask for and much harder
to use correctly.

**Ask for full history back to commissioning, not just the current rate.** The `alltime`
figure is the one that needs the deepest tail. If the API returns the current rate plus a
few years, `alltime` stays suppressed indefinitely and we gain `year_YYYY` but not the
total.

**Prices, not earnings.** The API should return prices rather than computed revenue, so
the integration can show its working (kWh × rate) and a member who thinks a figure is
wrong can see which input to challenge. An API-supplied earnings figure would have to be
taken on trust.

#### Pre-work that is safe to do now

- [ ] Extract the price lookup in `sensor.py` behind a single function, so the per-year
      table drops in later without touching the earnings logic
- [ ] Put the "no known price for this year → suppress, never fall back to a default"
      rule in one tested place. This is the rule most likely to be got wrong: silently
      applying a wrong price is precisely the failure the current suppression avoids.

#### Once the API lands

- [ ] Populate per-year prices; lift the `suppressed_no_historical_price` branch in
      `sensor.py:487`
- [ ] Compute `alltime` as a sum across years rather than suppressing it
- [ ] Deprecate the two `number` price entities, then remove them **in a later release
      only** — keep them until the API path has run for a release, and use the same
      backfill-first pattern as v4.13.6. Do not remove them in the same release that
      introduces the API path.

#### ⚠️ Coupling that must not be split

Per-year prices **break the precondition** of the "completed years are cached forever"
decision (`docs/development/decisions.md`). That decision is currently safe *only*
because no money is ever derived from a cached year. Adding per-year earnings makes
money derive from cached years, and financial figures can be corrected upstream in a way
generation much less so.

**These two changes land together or not at all.** A cached-year correction policy has to
be settled at the same time as the per-year price table, or the first retroactive board
restatement will silently serve stale earnings.

#### Open questions for the board

1. Is the CfD price per year, or per contract term? A CfD typically has a strike price
   that can be renegotiated, and may be flat across the whole term. If flat, the year
   dimension is mostly relevant to the owner price.
2. What happens for years with no known price? If the answer covers 2024 onward but not
   2022–23, those years must stay suppressed rather than fall back to a default.
3. Is the owner price per year and per turbine, or per year for the farm? The current
   owner price is farm-wide in pence per kWh.
4. Are retroactive corrections possible? If the board restates 2024, does that change
   history? This decides whether prices are immutable constants per release or a
   revisable data file — and therefore whether the caching question above is tractable.

### #37 — OAuth 2.1 PKCE authentication

- [ ] Add OAuth 2.1 Authorization Code flow with PKCE as alternative to manual API key entry (assigned: MJP-76)

### Dashboard & integration

- [ ] Rate limiting: classify 429 (`KirkHillRateLimitError`, honour `Retry-After` in the
      summary backoff) and expose `rate_limited` on the API status entity instead of folding
      it into `KirkHillConnectionError`. The API does return 429 — `tests/test_api.py:319`
      pins `HTTP 429 … Too many requests` — and the SCADA card already reads the attribute
      (`kirkhill-wind-scada-card.js:903`, `:2528`), so its amber "LIMITED" pill is dead code
      until this lands.
- [x] ~~Remove the deprecated turbine map card~~ — JS file already deleted; OBSOLETE_CARD_KEYS entry stays to prune old dashboards.
- [ ] 423 password-change-required → actionable reauth ("change your dashboard password, then
      reconfigure") via `ConfigEntryAuthFailed`, next to the existing 401/403 branches in
      `api.py`. Today a 423 becomes `KirkHillConnectionError`: last-known data held forever,
      API Status down, no hint of the cause — and a member changing their password is a
      member-doable event.
- [ ] `EntityCategory.DIAGNOSTIC` for the bookkeeping entities (`Latest import status`,
      `Data generated at`, `Unknown turbines`, `Data complete`, plus the new site capacity
      sensor) so they stay out of default dashboards and entity pickers. The integration
      uses `EntityCategory` nowhere today.
- [ ] Calendar month-to-date revenue + a 12-month `monthly` breakdown attribute
      (`{month, generation_kwh, revenue_gbp}` × 12) on the YTD value entity, for a
      revenue-by-month chart. Our `month` timeframe is a rolling 30d window, so that chart
      is impossible today. Needs `range=custom` with `from`/`to` (already on #55). Current
      months at the current price only — same basis as the existing YTD value, so the
      suppress-historical-£ decision is untouched.

## Code review backlog

- [x] Fetch the Open-Meteo forecast in parallel with timeframe summaries (was sequential; now runs as a parallel task when the slow tier is due, using cached turbine coordinates)
- [x] Investigate bare `except Exception` guards — both safe: dashboard load (YAML file, no API) and config flow (auth/connection errors caught first). No action needed.
- [x] `url_already_exists` string matching — replaced with `translation_key` attribute check (more robust than string matching against translated message)
- [x] ~~Split the ~700-line dashboard generation/merge logic out of `__init__.py`~~ — already done: `__init__.py` is 244 lines (setup/unload/listeners), `dashboard.py` is 519 lines (generation/merge/entity IDs).
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
- [x] Fix the test that let it through (see below)

Cost before the fix, at the default 60s scan interval: 2 wasted `get_summary` calls per
poll (~2,880/day), plus 14 more on each hourly slow poll (32 actual vs 18 intended,
because the first call populated `_immutable_year_summaries` and the second skipped only
the completed years).

### 🔴 No test can catch the duplicate — the assertion models the wrong property

`test_coordinator.py` asserts on a **set** of `(scope, range_value)` pairs, with a
comment saying this is deliberate ("so this cannot pass by coincidence"). A set is
invariant under duplication: it yields the same value for 2 calls as for 4, so the test
passes identically against the buggy and the correct implementation.

- [x] Change the schedule test from set-based to count-aware assertions
- [x] Add an API-call-budget regression test covering: normal poll, turbine-due poll,
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
the migration default of `0.0`. Deleting the RestoreEntity read path would silently reset
those users to £0 on every earnings sensor. (Correction: an earlier draft of this entry
said the default was 50.0. There is no 50.0 anywhere in the code — `const.py` has declared
`0.0` since the constants were introduced, and the 50.0 came from a commit message using
it as a hypothetical example.)

Note: the `f570578` RestoreEntity→options persist fix is doing more than its release note
claimed. It is the **only** path carrying pre-v4.12 prices into options, not just a
desync fix.

- [x] Test a ≤v4.11.6 upgrade with a populated `restore_state` and empty options before
      touching this — `test_number.py::TestPriceBackfillUpgrade`,
      `test_init.py::TestPriceBackfillMigration` (v4.13.6)
- [x] Make RestoreEntity a **one-time backfill** rather than a per-start override, so it
      cannot outrank options in steady state — v9 migration writes a
      `CONF_PRICE_RESTORE_PENDING` **list** into options; `_PriceBackfillMixin` consumes it
      once and deletes it (v4.13.6)
- [ ] Only then consider dropping `RestoreEntity`, and only in a release users reach from
      a version that already ran the backfill — every user has now run it exactly once
      during the v9 migration, so this is *unblocked*, but it is not urgent: the marker is
      what makes the steady state safe, and the read is skipped without it

Two things the naive fixes got wrong, both caught by the new tests:

- A **shared boolean** marker starves the second entity. Both numbers share one entry, so
  whichever set up first would clear the flag and the other price would never be
  recovered. The marker is a list; each entity removes only its own key.
- `merge_options` is a spread (`{**existing, **incoming}`), so it **cannot delete** a key.
  Popping the marker from the incoming dict left it in `existing`. It has to be removed
  from the merged result, or it survives into steady state and the stale-record clobber
  comes back.

There is deliberately **no** "value still equals the default, so backfill" shortcut.
`0.0` is a real value (`sensor.py` reports `projection_basis=no_owner_price_zero` for it),
so a value-equality guard would retry the restore forever.

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
- [ ] **PR B** — Fix the resulting lint debt (20 lines exceed the nested 88-char
      setting, not from new code)
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
- [ ] Split `dashboard.py` (529 lines) into `dashboard/{builder,merge,constants}.py`
- [ ] Extract frontend/JS static-path registration into `frontend.py`
- [ ] Extract payment-tracking setup (`_async_setup_payment_tracking`) into its own module
- [ ] Re-export from `__init__.py` where tests import `_CONFIG_ENTRY_VERSION` / `async_migrate_entry`
- [ ] Tests must pass unchanged at each step — refactor only, no behaviour changes
- [ ] **Deferred:** split the coordinator (490 lines / 21.9 KB) into summary / turbine /
      forecast managers. Both reviews agree this is premature until the API-call-budget
      test exists, because that test is what makes the split safe rather than another
      behavioural change. **That test now exists (`TestApiCallBudget`, v4.13.5), so the
      recorded blocker is cleared — only the split itself is still outstanding.**

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

### v4.15.2 (pre-release, 2026-10-09)

- Dashboard sign-in parked behind `SIGN_IN_ENABLED = False`: setup goes
  straight to the API-key form, because the key sign-in issues (56-char
  `kh_live_…`, same length and format as a working key) is rejected by the API
  with 401 "The API key is not valid."
- Nothing deleted — `oauth.py`, `describe_key`, the diagnostics, the permission
  gate and all OAuth tests stay and keep running in CI; re-enabling is one line
  plus a docs revert
- Docs return to key-only instructions, with a note on why sign-in is unavailable
- 215 → 216 tests (parked path asserted, re-enable path asserted)

### v4.15.1 (pre-release, 2026-10-09)

- A rejected sign-in key now reports its shape — length, format verdict and
  edge whitespace, never a character of the key — so "the dashboard rejected
  its own key" and "we sent the wrong bytes" are finally distinguishable
- The API client strips whitespace before building the Authorization header;
  one trailing newline is enough to produce this exact 401
- 6 new tests (209 → 215), the "never echo the key" property asserted directly
- Docs: `AGENTS.md`'s E501 claim corrected from 20 to **19** (re-measured with
  `ruff check .` as the text itself specifies)

### v4.15.0 (pre-release, 2026-10-08)

- Member savings sensor on the board's own basis: `owned watts × p/W`
  (2,559.465 W at 21p/W = £537.49), driven by a new `Owner rate (p/W)`
  number entity
- No timeframe and no accrual: an undeclared rate reads `unknown`, not
  `£0.00`; only a missing capacity reads `£0.00` (`no_capacity_zero`)
- Generation-based `Value (…)` sensors unchanged; alltime/past-year money
  still suppressed for want of rate history
- SCADA label "Your Share (W)" → "Your output (W)" (that row is live output,
  not owned capacity)
- 9 new tests (200 → 209)

### v4.14.2 (pre-release, 2026-10-08)

- A failed sign-in quotes the API's own message instead of one opaque
  sentence: `api.py` reads the error body before raising, so 401 carries
  `{"message": …}` and 429/5xx carry status *and* body (previously
  misreported as "cannot connect")
- `_validate_api_key` logs the verbatim reason and the sign-in abort quotes it
  through `{detail}`; exception types unchanged, so the reauth-vs-hold-data
  behaviour is untouched
- 8 new tests (192 → 200)

### v4.14.1 (pre-release, 2026-10-08)

- Validation probes **both** scopes now: an owner-only probe waved a
  share-only key through setup and stranded the site sensors on the next poll
- 403 classified as `KirkHillPermissionError` before `raise_for_status()`, so a
  permission problem stops reporting itself as a connection error
- Not an auth error: setup/sign-in name the consent option needed
  ("My share and whole wind farm"), and at runtime a 403 holds last-known data
  instead of starting re-auth — no coordinator changes, it lands in the existing
  non-auth `KirkHillApiError` paths
- Sign-in, paste and re-auth all require full access
- Docs: sign-in bullet and the README say which consent option to pick
- 8 new tests (184 → 192), three confirmed to fail against the previous code

### v4.14.0 (pre-release, 2026-10-08)

- Dashboard sign-in in the config flow (OAuth 2.1 + PKCE): the first step is a
  menu — sign in with your dashboard account, or paste an API key. The token
  *is* a `kh_live_*` key, so `entry.data`, options and everything downstream are
  unchanged; the paste path stays as the fallback
- Client registration happens once per redirect URI and is cached in a `Store`;
  endpoints are discovered, the registered URI is pinned, and each attempt gets a
  fresh PKCE verifier — no `OAuth2Session` is ever built, so the absent refresh
  token never matters
- Daily `OpenAPI sync` workflow refreshes `openapi.yaml` when the dashboard's
  build stamp moves and opens a PR listing new endpoints/schemas/fields with the
  contract-test result — it has already landed `/api/v1/carbon-avoided` and the
  `429` responses
- Docs: setup guides describe both paths, and the release references were updated
  across `CHANGELOG.md`, `installation.md`, `review-brief.md`, `decisions.md`,
  `info.md`
- 23 new tests (161 → 184)

### v4.13.9 (pre-release, 2026-10-06)

- Owner £ now follows the same fallback as owner kWh — a partial API failure
  could show £0.00 beside a non-zero kWh reading while claiming live-price maths
- `Capacity factor` and `Wind speed` no longer raise `KeyError` on an empty
  owner payload
- The `total_generation_kwh`/`total_kwh` lookup collapsed into `_summary_kwh`,
  one implementation for all three sites
- 4 new tests (157 → 161)

### v4.13.8 (pre-release, 2026-10-04)

- Release tooling: `version_sync.py release` pushes the tag before calling
  `gh release create`, and its guard checks `origin` instead of the local tag
  list — the v4.13.7 release had to be completed by hand. Four tests.
- Docs: the pre-release section was naming the wrong stable version
- No integration code changes; `custom_components/` is identical to v4.13.7

### v4.13.7 (pre-release, 2026-10-04)

- Reauth now reloads the entry — the new API key never reached the running
  client, so a successful reauth re-prompted about a minute later
- Domain-scoped `hass.data` services flag; the bare key collided with
  `flight_price_tracker` and either integration could lose its services
  silently
- Forecast task reaped on every exit path, and a malformed forecast payload no
  longer fails the whole update
- All time falls back to the API `range=all` figure when a year frame is
  missing instead of showing a partial sum 24–40% low
- `openapi.yaml` reconciled with the live API; fixtures split by endpoint and
  pinned to it by `test_openapi_contract.py`
- 19 new tests (134 → 153); `main`'s required checks recorded in `AGENTS.md`
  and `decisions.md`

### v4.13.6 (2026-10-01)

- `RestoreEntity` price read converted to a **one-time backfill** — the v9 migration
  writes a `CONF_PRICE_RESTORE_PENDING` list into options and the backfill consumes it
  once, so options is the sole authority in steady state with no pre-v4.13.0 price lost
- Removes the `hacs.json` `license` key (HACS rejects unlisted keys; the license check
  reads GitHub's SPDX metadata instead). HACS Validation green for the first time
- Config entry schema version 8 → 9
- 16 new tests: `TestPriceBackfillMigration`, `TestPriceBackfillUpgrade`,
  `TestRestoreDoesNotOverrideOptions`. Full suite 134 passed on current + minimum HA

### v4.13.5 (2026-10-01)

- Fix doubled summary fetch on every slow-tier poll (v4.13.4 regression)
- `_parse_data()` now guarantees a `dict`; a non-object `data` raises
  `KirkHillApiError` instead of leaking an `AttributeError`
- `TestApiCallBudget`: call-count assertions for the API budget (18 / 2 / 2 / 14)
- `AGENTS.md`: seven do-not-break invariants, each with its regression test named

### v4.13.4 (pre-release, 2026-10-01)

- SCADA card: remove clip paths, increase viewBox `wMax`

### v4.13.3 (pre-release, 2026-10-01)

- SCADA card: widen pills to fit text

### v4.13.2 (pre-release, 2026-10-01)

- SCADA card: fix text overflow on first load

### v4.13.1 (pre-release, 2026-10-01)

- Diagnostic sensors: `reading.complete`, `reading.generated_at`,
  `unknown_turbines`, `latest_import_status`, rotor-speed `sampled_at`
- API optimisation: drop the redundant `/api/v1/wind-speed` call, cache
  immutable year summaries, parallelise the Open-Meteo forecast with
  timeframe summaries
- Fix `url_already_exists` string match to use `translation_key`
- Docs: pre-release install/feedback, sensor reference, SUPPORT/CONTRIBUTING

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