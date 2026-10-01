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
  test exists.** It has grown to ~413 lines / 19 KB and does read like a god
  object (scheduling, API orchestration, historical caching, turbines,
  Open-Meteo, stale-state). Both external reviews reached the same conclusion:
  splitting it before the call budget is protected turns a refactor into another
  behavioural change, with nothing to catch the difference.

## Price persistence and historical caching

- **2026-10-01 — Prices set before v4.12 exist ONLY in `restore_state`. Do not
  remove the `RestoreEntity` read path without a replacement migration.** Up to
  v4.11.6, `number.async_set_native_value` wrote nowhere — it set the
  coordinator attribute and called `async_write_ha_state`, and that was it. So a
  user who set £85/MWh on v4.11.6 has that value in `restore_state` alone, while
  `options` holds only the schema migration default of 50.0. Deleting the
  restore read silently resets exactly the longest-tenured users on upgrade,
  because HACS users update to *latest* and will skip the intermediate release
  that carried the value across. The right shape is a **one-time backfill**
  (read restore, write options, then stop reading restore) before removal.
- **2026-10-01 — `RestoreEntity` must never outrank `entry.options`.** Since v8,
  options are the authoritative store. `number.async_added_to_hass` currently
  applies the restored value over options *unconditionally*, then persists it
  back — inverted precedence. In steady state the two agree (the number entity
  updates both, and the options flow never exposes prices), so it is not yet
  user-visible, but it is the wrong direction and should become a backfill.
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
  `_OBSOLETE_VIEW_PATHS` / `_OBSOLETE_CARD_KEYS` on merge.

## Deployment state

- **2026-09-17 — Production is aligned with the repository at `4.8.80`.**
  `CHANGELOG.md` is the authoritative version history. GitHub Releases/HACS are
  for other users; this host deploys from `origin/main` commits mirrored into
  `/homeassistant/custom_components/kirkhill_wind/`.

[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
