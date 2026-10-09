# Development decisions

Dated, one-line decisions with the reasoning behind them. This file is the
single place a future contributor (human or AI) can learn *why* the repository
is the way it is, without reconstructing intent from git history. User-facing
changes and version history live in the [`CHANGELOG`][changelog] and the docs;
this file is for internal constraints and trade-offs.

Nothing here is fixed forever — update an entry (or add a new one) whenever a
decision changes.

## Environment and production

- **2026-09-04 — This host (`172.16.1.2`) is production.** Editing the installed
  copy under `/homeassistant/custom_components/kirkhill_wind/` + reloading the
  config entry is an immediate production deploy. Dev is `172.16.1.3`. GitHub
  releases and HACS are for other users only and are not a gate for this box.
- **2026-09-04 — Any change under `custom_components/` needs a full HA restart.**
  There is no code reload. Do not restart without the owner's explicit go-ahead.
  Frontend JS (the SCADA card) can be hot-deployed via a config-entry reload and
  does not need a restart.

## Device registry

- **2026-09-04 — Turbines link to the farm hub via `via_device_id`, not the
  deprecated `via_device=(DOMAIN, entry.entry_id)` tuple.** The hub device id is
  resolved **once** during `async_setup_entry` in `__init__.py` via
  `get_farm_device_id(hass, entry)` (`async_get_or_create`) and stored on the
  coordinator, before platform setups are forwarded. Required for HA Core
  2027.8 compatibility.
- **2026-09-04 — The farm hub is a `SERVICE` device** (`entry_type=SERVICE`,
  identifiers `(DOMAIN, entry.entry_id)`); turbines are separate physical
  devices linked to it via `via_device_id`.

## Release and HACS

- **2026-09-04 — HACS reads GitHub Releases, not tags.** a tag alone is not
  enough for HACS to pick up an update. Always publish a GitHub Release for a
  version users are meant to install.
- **Version source of truth is the root `VERSION` file**, propagated by
  `scripts/version_sync.py` to `manifest.json` and `pyproject.toml`. See
  [release-management](release-management.md).
- **2026-10-04 — `main` requires all three CI checks; push a branch and open a
  PR.** Branch protection now lists `validate` / `test` / `min-ha` as required
  status checks, so a direct `git push` to `main` is declined (`GH006`) —
  checks cannot report on commits that exist only locally. AGENTS.md
  previously recorded the opposite ("main has no branch protection").

## Code health

- **2026-09-04 — Dead code and unused imports removed to satisfy ruff** in the
  validate workflow (F401 unused imports, F841 unused local variables, E501 line
  length). Removed: `owner_value_entities`, `site_value_entities`, `kpi_cards`
  in `__init__.py`, and unused imports in `coordinator.py` / `sensor.py`. All
  were confirmed unused (single occurrence each); no live references.

## Config entry schema and API boundary

- **2026-10-01 — Schema v8: `entry.data` holds connection only (`api_key`,
  `base_url`); every setting lives in `entry.options`, and options are
  authoritative.** Before v8 both lived in `data`, which meant reading a setting
  and reading a credential were indistinguishable. Reads go through
  `settings.py` (`get_setting`, `get_scan_interval`, `get_site_name`, …) rather
  than touching `entry.data` directly — that indirection is the enforcement
  point for this rule.
- **2026-10-01 — Every writer of `entry.options` must go through
  `settings.merge_options`, never a bare dict literal.** Home Assistant
  *replaces* the options mapping wholesale on `async_create_entry`
  (`config_entries.py`, `MappingProxyType(options)`), it does not merge. The
  options flow used to pass only its own three form fields, so opening the
  Options dialog and saving silently deleted the CfD and owner prices that
  `number.py` persists. `merge_options(existing, incoming)` is the single
  enforcement point; `getattr`-style fallbacks elsewhere are not a substitute.
- **2026-10-01 — The v8 migration uses `setdefault`, so pre-existing options win
  over `data`.** Options already took precedence at runtime, so copying `data`
  over the top would have rolled a user's setting backwards — the exact failure
  `test_existing_options_win_over_data` guards.
- **2026-10-01 — `_parse_data()` guarantees a `dict`; callers may rely on it.**
  Every caller does `payload.get(...)` immediately afterwards, so a
  `{"data": []}` response would raise a bare `AttributeError` from inside the
  client — not a `KirkHillApiError` — and the coordinator's stale-data and
  retry-backoff machinery would never engage. In `get_turbines()` this fired
  *before* that method's own `isinstance` guard. Validate once at the boundary,
  not at each call site.
- **2026-10-01 — The per-poll API call budget is a contract, not an
  implementation detail.** Assert call **counts**, not sets. A set of
  `(scope, range)` pairs is invariant under duplication, so a set-based
  assertion passes identically whether a timeframe is fetched once or twice —
  which is exactly how a doubled summary fetch shipped in v4.13.4. See
  `TestApiCallBudget` in `tests/test_coordinator.py`.

## Coordinator scheduling

- **2026-10-01 — Summary fetches are issued exactly once per
  `_async_update_data()`, after the turbine tier, never inside the initial
  `asyncio.gather`.** `_next_slow_update` is only advanced *after* the summary
  call, so an earlier invocation also saw the slow tier as due and duplicated
  every summary request (2 wasted calls per 60s poll, plus 14 on the hourly slow
  poll). The ordering is deliberate: the turbine tier refreshes the cached
  coordinates the Open-Meteo forecast depends on, so summaries must not start
  before it.
- **2026-10-01 — The coordinator is not to be split until the API-call-budget
  test exists.** That test now exists (`TestApiCallBudget`, v4.13.5), so the
  recorded blocker is cleared; the split itself is still deferred. The file has
  grown to 499 lines / 22.5 KB and does read like a god object (scheduling, API
  orchestration, historical caching, turbines, Open-Meteo, stale-state). Both
  external reviews reached the same conclusion: splitting it before the call
  budget is protected turns a refactor into another behavioural change, with
  nothing to catch the difference.

## Price persistence and historical caching

- **2026-10-01 — Prices set before v4.13.0 exist ONLY in `restore_state`. Do not
  remove the `RestoreEntity` read path without a replacement migration.** Up to
  v4.11.6, `number.async_set_native_value` wrote nowhere — it set the
  coordinator attribute and called `async_write_ha_state`, and that was it. So a
  user who set £85/MWh on v4.11.6 has that value in `restore_state` alone, while
  `options` holds only the schema migration default, which is `0.0` (`const.py`
  has declared `DEFAULT_CFD_PRICE_GBP_PER_MWH = 0.0` and
  `DEFAULT_OWNER_PRICE_PENCE_PER_KWH = 0.0` since those constants were
  introduced). Deleting the restore read silently zeroes every earnings sensor
  for exactly the longest-tenured users on upgrade, because HACS users update to
  *latest* and will skip the intermediate release that carried the value across.
  The failure is silent, not loud: `sensor.py` reports
  `projection_basis=no_owner_price_zero` and returns `0.0`, with nothing raising.
  A note on the record: an earlier version of this entry, and of `TODO.md`, said
  the fallback was 50.0. That figure came from the `f570578` commit message,
  which used 50.0 as a hypothetical stale default rather than a real one.
- **2026-10-01 — `RestoreEntity` must never outrank `entry.options`.** Since v8,
  options are the authoritative store. `number.async_added_to_hass` applied the
  restored value over options *unconditionally*, then persisted it back —
  inverted precedence. In steady state the two agree (the number entity updates
  both, and the options flow never exposes prices), so it was not user-visible,
  but the direction was wrong. **Resolved in v4.13.6** by the backfill below.
- **2026-10-01 (v4.13.6) — The restore read is a one-shot backfill, gated on a
  marker in options.** The v9 migration writes `CONF_PRICE_RESTORE_PENDING` for
  any pre-v9 entry; `_PriceBackfillMixin` reads `restore_state` only when the
  marker is present, persists the recovered value, and removes its key. The
  marker is the *only* thing that distinguishes "never set" from "set before
  persistence existed", because the v5/v6 migrations seed the key and so
  `options` always contains it after migration. Three design points that are
  load-bearing and easy to undo:
  - The marker is a **list of option keys**, not a boolean. Both number entities
    share one config entry; a shared boolean lets whichever sets up first clear
    it, stranding the other price in `restore_state` forever.
  - `merge_options` is a spread, so it **cannot delete** a key. The marker must
    be popped from the merged result, or it survives into the steady state and
    the stale-record clobber returns.
  - There is deliberately **no** "value still equals the default" shortcut. `0.0`
    is a legitimate value — `sensor.py` reports `no_owner_price_zero` for it — so
    a value-equality guard would retry the backfill forever.
  Every user has now run the backfill exactly once during the v9 migration, so
  dropping `RestoreEntity` is technically unblocked. It is still not worth doing
  on its own: the marker is what makes the steady state safe, and with the
  marker absent the read is already skipped.
- **2026-10-01 — Completed calendar years are fetched once and cached for the
  lifetime of the process.** `year_YYYY` frames below the current year are
  immutable: fetched, stored in `_immutable_year_summaries` /
  `_immutable_year_windows`, and skipped thereafter. This is safe **only**
  because no money is ever derived from them — `sensor.py` returns `None` for
  `alltime` and every `year_*` timeframe (see the 2026-09-29 decision above), so
  the only exposure is generation kWh for completed years. If the API ever gains
  a revenue or settlement field, revisit: financial figures can be corrected
  upstream and generation much less so.

## Owner share and earnings figures

- **2026-09-04 — Owner share % is watt-based and derived from the API, not
  configured.** The share equals `owner capacity_watts / site capacity_watts`
  from `/api/v1/current`. Buying more watts raises it automatically. The old
  `owner_share_percent` config field was removed (config version 3 → 4) because
  a user-entered % would go stale and because the previous generation-ratio
  derivation was cached forever.
- **2026-09-04 — The projected annual earnings (GBP) are live-editable via
  `number` entities, not only config.** Owner and site projected-earnings are
  exposed as integration `number` entities seeded from the config entry, and
  the financial sensors read them live from the coordinator. Values persist
  across restarts (`RestoreEntity`), so a user can adjust figures without
  reconfiguring when new share/watt data becomes available.
- **2026-09-16 — A negotiated CfD price (GBP/MWh) switches the £ column to
  live-accurate calculation.** A `number` entity (`negotiated_price_gbp_mwh`)
  stores the negotiated price. When set (>0), each timeframe's £ value is
  `actual generation kWh ÷ 1000 × price`; when 0 or live kWh is unavailable it
  falls back to the projected model. The alltime timeframe keeps the fallback
  path because no historical price data exists — the projected model cannot be
  replaced there without price history.
- **2026-09-29 — All-time and past-year £ values are suppressed (`unknown`,
  card shows `—`) until the CfD strike price history is clarified.** The API
  records energy only, never money; computing these values as
  `kWh × current price` would silently revalue history every time the price is
  edited. This applies to the All time row and the past-year value sensors
  (2025, 2024). The kWh energy figures remain live. All other timeframes keep
  their live £ figures. To revisit once the CfD strike price value(s), whether
  the CfD has ever changed, and its contract length are confirmed. When known,
  each year gets its own price — the per-year sensors are the foundation for
  the multi-CfD price schedule.
- **2026-09-29 — All time generation is the calculated sum of the per-year
  sensors, and the past-year figures stay off the SCADA card.** The user wants
  `2024 + 2025 + … + the current year to date (+ future years)` to equal the
  All time figure exactly, so the All time kWh sensor sums every year-based
  timeframe (`year` + `year_YYYY`) instead of trusting the API's `range=all`
  total. Past-year figures exist as sensors only — they are deliberately not
  shown in the card's generation/finance panels. The year list is derived from
  the commissioning year (2024) to the last complete year, so future years join
  the sum automatically; their sensors appear after the next restart.
- **2026-10-04 — When a year frame is missing, All time reports the API's
  `range=all` figure rather than a partial sum.** *Qualifies the 2026-09-29
  sum decision directly above; the sum stays the normal path.* A year frame
  whose fetch fails arrives as `{}` and sits in retry backoff for up to an
  hour, and `_sum_yearly_kwh` used to skip it silently: All time read 24-40%
  low (2024 alone is a quarter of the total) while the attribute still claimed
  `sum_of_years`. The API's own all-time figure is wrong by ~0.1% instead,
  because that window trails the latest import. The sensor now says which of
  the two it is: `generation_source=api_alltime_missing_years` plus
  `missing_year_frames`, or `sum_of_years` when every frame is present.
  Regression test: `test_sensor.py::TestAlltimeYearSum`.
- **2026-09-29 — The projected-annual-earnings estimates are removed (config
  version 7).** *Supersedes the 2026-09-04 decision above.* The owner/site
  projected annual earnings (default £132 / £0) were estimated averages feeding
  a projected model that v4.11.5 retired: earnings are now `kWh × real price`
  or `£0.00` when no price is set, so the estimates drove no displayed value.
  The config-flow fields, the `Projected annual earnings` number entities, the
  `projected_annual_gbp`/`projection_factor` attributes and the dead
  `_cfd_price_gbp_per_mwh()` helper are all gone, and the v7 migration strips
  the stale keys from existing entries. The real prices (with their effective
  dates) are being sourced from the co-op board — when they land, per-year
  prices replace the estimates entirely.
- **2026-10-08 — Member savings are capacity-based (`W × p/W`), a second money
  basis beside `kWh × price`.** Confirmed by the board's announcement and by
  Klaus Dudas in discussion: *"payment is based per Watt owned, not per kWh
  generated"*, and *"time frame doesn't come into the calculation at all"* —
  1,000 W at 21p/W is £210 for whatever span the board declares, so
  2,559.465 W is £537.49 for Feb 2025–Jun 2026 (£1.6M across ~7.62 MW of
  member-owned capacity). The new `Member savings value` sensor multiplies the
  API's owner `capacity_watts` by an `Owner rate (p/W)` number entity and
  deliberately has **no timeframe and no accrual**: the payment is
  retrospective — the board reviews its finances and declares a "dividend"
  when it declares one, so no effective earning rate exists until then, which
  is why the web dashboard shows no ongoing earnings at all. The board's "15p
  per watt per 12 months" is an *equivalence for that one declaration*, not a
  rate to divide over time; deriving a daily accrual would invent a figure
  nobody published — the same failure the 2026-09-29 suppression decision
  exists to avoid. The `Value (…)` sensors keep their `kWh × price` meaning
  untouched (that is the pre-move Ripple model; they answer a different
  question), and All time / past-year money stays `unknown`, because there is
  no rate history to value it with. **No declared rate (`0.0`) reads
  `unknown`, not £0.00** — asserting zero would be a statement the board never
  made; `projection_basis` is `no_rate_declared`, with `no_capacity_zero` +
  £0.00 reserved for genuinely having no watts to pay on. The rate is updated
  whenever a payment is declared. Neither figure is shown on the SCADA card.
  Regression tests: `test_sensor.py::TestMemberSavingsValue` (pins 537.49 and
  the undeclared-`unknown` behaviour), `test_number.py` (rate persistence).
- **2026-10-09 — All earnings figures are hidden until the board defines the
  model.** *Supersedes the display half of the 2026-10-08 entry above.* Two
  bases had collided on one card: the timeframe `Value (£)` column
  (`kWh × p/kWh`) and the capacity figure (`watts × p/W`) — and when the owner
  price was back at 21 p/kWh, the column reported ~£1,350 for a year against
  the board's £537.49 for 17 months. Rather than keep choosing between them,
  money is backed out entirely, reversibly:

  - **22 entities disabled** in the registry (`disabled_by: user`): the 19
    value/savings sensors and all 3 `number` inputs
  - **all three inputs zeroed** — `owner_price_p_kwh`, `owner_rate_p_w`,
    `negotiated_price_gbp_mwh` all `0.0`
  - **card no longer renders** the `Value (£)` column (both panels), either
    live `£/h` rate, either price pill, or the member-savings line

  Generation, power, capacity, wind and share are untouched. **Nothing was
  deleted:** the sensor classes, `number` entities and even the card's render
  code remain, so restoring is `hab entity enable` plus re-adding markup —
  deliberate, because the back-out is explicitly *"for now"*. The one layout
  consequence: `widestFin` no longer exists, so the generation column's clamp
  is now just the panel's right edge.

  Revisit when the board answers three things: the per-watt rate and the period
  it covers, whether a period counts before it is declared, and how `All time`
  accumulates across declared periods (a ledger of `Σ watts × rate` per
  declaration, not a time integral).

## Dashboard consolidation

- **2026-09-16 — SCADA is the sole live dashboard; History, Finances and
  Turbines are consolidated.** History's 25h charts are covered by SCADA Owner/Site
  modals (6H–1Y). The Finances tab was retired in v4.8.79: its earnings figures
  (today, this month, YTD) now render as a per-timeframe **£ value column** inside
  the SCADA card's **Owner Capacity** and **Site Capacity** panels (both Owner and
  Site scopes), and the right-side panels gained a "Generation, Capacity &
  Earnings" heading. The Turbines tab was removed in v4.8.80: the standalone map
  and per-turbine status overview no longer ship — per-turbine power, status, and
  today's generation live on the SCADA diagram, per-turbine history in each
  pop-out, and the coordinates in the turbine modal link to Google Maps. Existing
  installs prune History, Finances and Turbines views via
  `OBSOLETE_VIEW_PATHS` / `OBSOLETE_CARD_KEYS` on merge.

## Deployment state

- **2026-10-09 — The repository is at `4.16.1` (pre-release); production runs
  `4.15.1`.** Nothing is deployed by releasing: the changed files under
  `custom_components/kirkhill_wind/` reach this host only when `origin/main` is
  mirrored into `/homeassistant/custom_components/kirkhill_wind/` and Home
  Assistant is fully restarted — which needs the owner's explicit go-ahead.
  `CHANGELOG.md` is the authoritative version history. GitHub Releases/HACS are
  for other users; this host deploys from `origin/main` commits mirrored into
  `/homeassistant/custom_components/kirkhill_wind/`.

[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
