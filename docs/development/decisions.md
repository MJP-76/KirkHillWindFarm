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
  a co-op representative in discussion: *"payment is based per Watt owned,
  not per kWh generated"*, and *"time frame doesn't come into the calculation
  at all"* — 1,000 W at a declared 20p/W is £200 for whatever span the board
  declares. The new `Member savings value` sensor multiplies the
  API's owner `capacity_watts` by an `Owner rate (p/W)` number entity and
  deliberately has **no timeframe and no accrual**: the payment is
  retrospective — the board reviews its finances and declares a "dividend"
  when it declares one, so no effective earning rate exists until then, which
  is why the web dashboard shows no ongoing earnings at all. A yearly figure
  the board quotes is an *equivalence for that one declaration*, not a
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
  Regression tests: `test_sensor.py::TestMemberSavingsValue` (pins the example
  figures and the undeclared-`unknown` behaviour), `test_number.py` (rate persistence).
- **2026-10-09 — All earnings figures are hidden until the board defines the
  model.** *Supersedes the display half of the 2026-10-08 entry above.* Two
  bases had collided on one card: the timeframe `Value (£)` column
  (`kWh × p/kWh`) and the capacity figure (`watts × p/W`) — and with the owner
  price set to a per-kWh value the column reported figures an order of
  magnitude away from what the board actually pays. Rather than keep choosing
  between them, money is switched off everywhere, reversibly:

  - **22 entities disabled** in the registry (`disabled_by: user`): the 19
    value/savings sensors and all 3 `number` inputs
  - **all three inputs zeroed** — `owner_price_p_kwh`, `owner_rate_p_w`,
    `negotiated_price_gbp_mwh` all `0.0`
  - **card renders the money UI empty** — the `Value (£)` column (both panels),
    both `£/h` cells, both price pills and the member-savings line are drawn but
    unpopulated (every money cell `—`), *amended the same day: the maintainer
    preferred the empty layout back as a standing visual reminder to finish the
    work, rather than the columns disappearing*. The Owner pill was rewired from
    p/kWh to the **p/W rate**, the board's basis.

  Generation, power, capacity, wind and share are untouched. **Nothing was
  deleted:** the sensor classes and `number` entities remain, and v4.16.2 put
  the card's markup and render code back — drawn but empty — so bringing a
  figure back is now only `hab entity enable`. Deliberate, because the back-out
  is explicitly *"for now"*.

  Revisit when the board answers three things: the per-watt rate and the period
  it covers, whether a period counts before it is declared, and how `All time`
  accumulates across declared periods (a ledger of `Σ watts × rate` per
  declaration, not a time integral).

- **2026-10-12 — Config version 11 purges the earnings inputs outright.**
  *A consequence of the 2026-10-09 hold.* An in-place upgrade was expected to
  clear the stored inputs and did not: `entry.options` survives upgrades by
  design, so a zeroed input simply stayed stored. **v10** removed any of the
  three (`owner_price_pence_per_kwh`, `owner_rate_pence_per_w`,
  `cfd_price_gbp_per_mwh`) still at its declared default and spared a
  configured one — which on the production install was precisely the case that
  mattered: its values were non-zero, so the upgrade cleared nothing at all.
  **v11** therefore purges the keys whatever they hold, and the v9 backfill
  marker with them: leaving the marker would let `restore_state` resurrect a
  purged price on the very next setup.

  `settings.SETTING_DEFAULTS` still declares the keys, so `get_setting()`
  answers `0.0` and runtime behaviour is unchanged — the values simply stop
  existing. `number.py`'s `RestoreEntity` read path is untouched (AGENTS.md
  rule 3); a migrated entry can just never carry a marker again.

  The cost is deliberate and should be re-read before the hold lifts: **any
  configured monetary value on any install is deleted by the next upgrade**, so
  the values have to be re-entered when the board's model is settled. New
  entries are created at v11 by `config_flow.VERSION`, which a test keeps in
  step.

  Regression tests: `test_init.py::TestMonetaryInputsPurged` (defaults purged,
  configured price purged, marker purged, current entry untouched).

- **2026-10-21 — All time is a ledger of declared periods: dated p/W line
  items, summed.** *Answers the three open questions the 2026-10-09 hold left
  for the board, and partially lifts that hold at the owner's instruction ("we
  are starting to put back onto the tab").* The AGM sets a twice-a-year rhythm,
  but the exact payment dates are not settled, so a period is a pair of
  **editable dates** rather than a rule the code enforces: a historical span is
  split at the half-year mark for readability and can be re-dated later without
  changing any figure, because the rate — not the calendar — produces the
  money (`capacity_watts × rate_p_per_w ÷ 100`). A period is never integrated
  over time; 2,000 W at 20 p/W is GBP 400 for whatever span the board declares.

  - **New `payment_ledger.py`**, a `Store`-backed list per config entry of
    `{period_start, period_end, rate_p_per_w, capacity_watts, announced_on,
    note}`. **Capacity is stored with the declaration** because owned watts can
    change: valuing Feb 2025 → Jun 2026 at *today's* capacity would silently
    misprice history — the same class of error the all-time suppression exists
    to avoid. Storage is `kirkhill_wind_payment_ledger_<entry_id>`, a `Store`
    and never `entry.options`, because v11 purges earnings inputs whatever they
    hold (2026-10-12).
  - **New `sensor.…_payment_ledger`.** State is the declared total, which
    reads **unknown while no record exists — never GBP 0.00**: no declaration
    is not a declaration of nothing. Attributes carry `records`, `total_gbp`,
    `latest_rate_p_per_w`, `latest_period_*` and `current_gbp` +
    `current_basis`. It is always available — a failed API poll must not blank
    figures that live on disk.
  - **The estimate is labelled, and never counted.** *(Superseded later the
    same day by the withholding rule below.)* When today was past every
    declared period the pending period was priced at the last announced rate
    and drawn `~` — derived, marked, never presented as announced, and never
    added to `total_gbp`. It also answered "does a period count before it is
    declared": **no.**
  - **Exactly three cells return, and no more:** the Owner pill (the latest
    published p/W rate — deliberately no money on the pill, so it does not
    repeat the row below it — and also the pop-out's entry point), the Owner
    panel's **All time £**
    (the ledger total in place of the suppressed `kWh × price`) and **Member
    savings** (the current period). Every other money cell — the timeframe £
    column, both £/h cells, the Site panel — stays suppressed, and all 22
    earnings entities stay disabled and zeroed.
  - **Three services are the only write path** —
    `kirkhill_wind.add/update/remove_payment_record`; the card never writes
    storage itself. A new record defaults its capacity to the owner watts the
    API reports, and is **refused rather than guessed** when the API is not
    reporting any. A p/W rate of `0` is rejected by the schema: "nothing
    declared" is expressed by having no record.
  - Backed out by deleting the sensor's entity and the ledger file; the card
    falls back to its old single-rate pill if `payment_ledger_entity` is absent
    from a stored dashboard.

  Regression tests: `tests/test_payment_ledger.py` (validation · Σ ·
  empty-reads-unknown · estimate labelling · persistence and sort · listener
  notify/unsubscribe · per-service behaviour · zero-rate schema rejection),
  `test_services.py::TestServiceRegistrationFlag` (five services registered and
  unloaded).

- **2026-10-21 — Periods are whole months, and a new line offers the month
  after the latest one.** *Refines the ledger entry above, after reviewing it
  on the live install.* The board does not settle payment dates to a day — it
  declared "Feb 2025 to June 2026" and the AGM sets the twice-yearly rhythm —
  so a day-level period would assert precision nobody has published, and every
  later re-date would look like a different declaration.

  - **Stored periods are month-granular.** `normalise_record` snaps
    `period_start` to the 1st and `period_end` to the last day of its month
    (leap February included), **after** the end-not-before-start check, so a
    backwards period stays an error instead of widening into a valid month.
    `YYYY-MM` is accepted as input and resolves the same way. One place does
    this — `payment_ledger.py` — so a record is aligned whichever door it came
    in by: the card, the service, or a hand-edited storage file.
  - **The card's form deals in months, not days** (`type="month"`, `YYYY-MM`),
    validates both fields before calling the service, and expands them to the
    1st/last day it sends. Rows read `Feb 2025 – Jun 2026`.
  - **Adding a line prefills the start with the month after the latest period
    ends** (Jun 2026 offers `2026-07`) and leaves the end blank: only the start
    follows from what is already declared — when the next period closes is the
    board's to say, not ours to guess. Editing keeps the stored months.
  - Stored shape, service schemas and `total_gbp` are untouched: precision was
    removed, the model did not change, so an existing record survives an
    upgrade unmoved (the live one already read 1 Feb 2025 – 30 Jun 2026).

  Regression tests: `tests/test_payment_ledger.py::TestNormaliseRecord` (month
  snap · month-only shorthand · leap February · backwards period still
  rejected).

- **2026-10-21 — Money leaves the SCADA card entirely; a dedicated
  Return-on-investment card owns it.** *Supersedes the "three cells return"
  half of the ledger entry above and the same-day "Year + YTD" refinement
  (neither ever shipped to a user's eyes in final form).* Reviewing the live
  card showed the result of scattering money across a generation display: seven
  timeframe rows that could not honestly carry a figure, two panels asking two
  different money questions, and an Owner pill that had changed meaning three
  times. The owner's call: **all money off the Owner and Site panels** — and,
  once a standalone tab existed to look at, *"the ROI needs to be displayed the
  same as site / owner cards"*. Finance ended the day as a **third panel on the
  SCADA card**, with its detail in a modal.

  - **Removed from the Owner and Site panels:** the `Value (£)` column, both
    `£/h` cells, the Member savings line, both price pills, the ledger pop-out,
    and every config key that fed them (`owner_price_entity`,
    `owner_rate_entity`, `negotiated_price_entity`, `member_savings_entity`,
    plus `value_entity` in the generation lists). Generation now owns the
    right-hand edge of both panels instead of leaving the old money column's
    gap. `payment_ledger_entity` stayed: the new panel reads it. The SCADA card
    went 3069 → 2878 lines before the panel brought some back.
  - **A third panel, `Return on investment`, below the Site panel** — the same
    232-unit box, the same `Measure | Value` columns, the same `site-gen`
    styling and click affordance, because it is meant to read as one of the
    family. It carries the headline only: invested, declared total, board /
    self split, return, period count, published rate (board declarations only)
    and the current period (`~` while pending or self-estimated). **Clicking it
    opens the ledger modal** — rows with edit and remove, the capital input and
    both forms — the exact panel-plus-modal pattern Owner and Site already use.
    A standalone `custom:kirkhill-wind-roi` card in its own `roi` view existed
    for part of the same day; it is deleted rather than left unreferenced, and
    the view is in `OBSOLETE_VIEW_PATHS` so installed dashboards lose the
    orphaned tab on the next setup.
  - **ROI is plain percentage of capital per period**: `value ÷ invested × 100`,
    **deliberately unannualised** — the board pays per period regardless of how
    long it runs (2026-10-08), so a per-year figure would be a rate of our own
    invention. No invested amount reads **None**, never `0%`: unknown capital
    is not a zero return.
  - **`invested_gbp` is stored in the ledger's Store beside the records**,
    written by the new `kirkhill_wind.set_invested_amount` service (JSON null
    clears it back to "not told"), and saved in the same commit as the records
    so a return can never be computed from half a save. Never
    `entry.options` — v11 purges monetary keys there (2026-10-12).
  - **Each record carries a `source`** — `board` (announced) or `self` (the
    member's own estimate; the form's "Board announced" box is pre-ticked, and
    records predating the field normalise to `board`). The total still sums
    both, while `board_total_gbp` / `self_total_gbp` say how much of it was
    announced, `self` rows are tagged and `~`-prefixed, and **only board
    records feed `latest_board_rate_p_per_w`** — a self estimate is not a
    published rate.
  - **Timeframe rows stay empty on the SCADA card**, as decided earlier the
    same day: Yesterday…Year are `kWh × price` sensors that remain disabled,
    and slicing a per-watt declaration across days would be the accrual the
    board's basis rules out. The ledger still exposes `current_year_gbp` and
    `year_totals_gbp` (declarations attributed whole to the year they *end* in)
    for templates.
  - PR #113 (the All time cell write fix) was closed unfixed: the cell it
    repaired is one of the cells being removed.

  Regression tests: `test_payment_ledger.py` (source validation · board/self
  split · board-only published rate · year attribution · invested persistence ·
  `roi_pct` rules · null-not-zero · service round trip) — 266 → 289;
  `test_services.py` (six services). The panel and its modal are frontend: CI
  has no browser, so they need an eyeball on a real instance.

- **2026-10-21 (later) — estimates are withheld outright, and the ROI panel
  moves above Owner.** *Supersedes the "estimate is labelled" bullet above and
  the earlier panel position.* Two owner inputs, after seeing it live:

  - **No estimate until the board's split exists.** Every payment is going to
    divide into **capital and interest**, and the split is unknown — so a
    figure of unknown composition cannot be estimated honestly: a derived
    number would be neither what the board pays nor safely ignorable (decision
    note `2026-10-21-payments-split-into-capital-and`). `current_figure` now
    returns **`(None, estimate_withheld_split_unknown)`** for an undeclared
    period instead of pricing it at the last announced rate: the panel's
    *Current period* row draws `—`, the modal caption says nothing, and only a
    self-entered record can still show `~`. Declared periods, totals and ROI
    are untouched, and `current_source` still reports so a self entry remains
    distinguishable. Backing it out means restoring the derivation and the
    literal basis string `estimated_from_last_declared_rate`.
  - **The panel sits at the top of the right column:** order is
    Return on investment (y=76, 192 units for six rows) → Owner (292) → Site
    (548), each with a 24-unit gap and clear of the National Grid box (914) —
    finance first, in the same box and columns as the panels it leads.
  - **Two rows dropped from it the next day**, on the owner's call: **Published
    rate** and **Current period**. Both only summarised what the modal already
    carries per period — the rate sits on every row there (and only board
    records ever set it), while the current period is blank whenever a period
    is undeclared and the modal's caption can also say *who* declared it. Six
    rows remain: Invested · Payments from Co-op · Your estimates · All Payments
    · Return · Periods. Both figures are still exposed as attributes
    (`latest_board_rate_p_per_w`, `current_gbp`, `current_basis`,
    `current_source`).

  - **On-screen wording and order, the same day.** The three figures read
    **Payments from Co-op · Your estimates · All Payments**, in that order —
    components before the sum, on the owner's instruction. They had been
    *All periods · From the board · Your estimates* earlier the same day, and
    "declared" before that, doing double duty (it meant *in the ledger*, not
    *said by the board*), so provenance is carried by **Co-op** vs **yours**
    everywhere the user looks: the modal stats, the `your estimate` row tag,
    the *Announced by the board* tick, and both captions. Display strings only
    — attribute keys and values (`total_gbp`, `board_total_gbp`,
    `self_total_gbp`, `current_basis=declared`) are deliberately unchanged, so
    templates, tests and the documented attribute list stay valid.

  Regression tests: `test_payment_ledger.py` (withheld basis · figure is None ·
  source still reported · total unchanged) — 289 passing.

- **2026-10-22 (later) — the withheld basis says what it is waiting for.**
  The Feb 2025–Jun 2026 record gained a hand-entered split (0 / £537.49) and
  the attribute still read `estimate_withheld_split_unknown` — claiming the
  split was the missing piece when `current_figure` was in fact withholding
  because **today sits past every declared period**. The value is now
  `awaiting_next_declaration`: a declaration brings the rate *and* the split
  together, so that is what is being awaited. The panel's *Current period*
  caption, previously blank in that state, now reads *awaiting the board's
  next declaration* — still no invented number. Tests pin the literal through
  `BASIS_WITHHELD`; backing it out means restoring the old string in
  `payment_ledger.py`, the card caption, `dashboard.md`, `sensors.md` and the
  test that pins it.

- **2026-10-22 (later) — lifetime estimate, derived share value, green
  invested.** Three additions on the owner's call, for the 4.18.2 line:

  - **Lifetime = known + time-left, never an accrual:** the board's actuals
    plus `(lifespan − elapsed since the first board period) × watts × stored
    annual rate ÷ 100`, elapsed fractional (days ÷ 365.25; no periods means
    no anchor and elapsed zero). The annual rate is the member's projection
    input — normally the board's 15 p/W equivalent — read from the Store
    where it has always lived, never a constant in this code, because the
    board can requote (2026-10-22's projection rule is unchanged: labelled,
    counts for nothing, `total_roi_pct` stays the factual return). Shown in
    the **projection modal only** — the panel keeps its six rows
    (2026-10-21 (later)).
  - **Share value is derived:** `invested_gbp ÷ capacity_watts`, exposed as
    `share_value_gbp_per_w` and quoted in the invested form (*≈ £1.7300/W ×
    2,559.465 W*). Nothing stores it and it writes nothing back — a quotation
    of the two figures beside it, not a figure of its own.
  - **Green = you typed it.** The panel's Invested cell, the modal's Invested
    value and its input take `--success-color` whenever `invested_gbp` has a
    value, because every path that can set it is a user path; unset keeps the
    normal colour and says `Not set`. If a derived invested source ever
    appears, provenance needs its own flag then.

  Regression tests: `TestLifetimeEstimateAndShareValue` (10) — 334 passing.

- **2026-10-22 — The capital/interest split is entered by hand, now.**
  *Supersedes "no code until the board publishes the split".* The owner's call
  after v4.17.0 shipped: the split comes from an **Ethex statement or a board
  announcement**, so waiting for the board's rule was waiting for nothing — and
  manual entry may simply stay the easier route once the rule exists.

  - **Two optional fields per record**, `capital_gbp` and `interest_gbp`.
    Enter **either half** and the other is completed from the period's figure;
    enter **both** and they must sum to it **to the penny** — a mismatch is
    rejected (`capital + interest (£400.50) must equal the period's figure
    (£400.00)`), and the same check fires on a later edit to that period's rate
    or watts, so a stored pair can never drift from its record. Nothing else
    ever derives a split: absent both halves, a record simply has none.
  - **Modal only**, by the owner's choice: rows gain
    `Capital £400.00 · Interest £137.49`, a line under the totals sums them
    (`Of £1,074.98 recorded: £800.00 capital · £274.98 interest`), and the form
    gains both fields with the penny rule spelled out. The panel keeps its
    eight rows; nothing about Owner or Site moves.
  - **Attributes**: `capital_gbp` / `interest_gbp` per record, and
    `capital_total_gbp` / `interest_total_gbp` at the ledger — each `None`
    while no record carries that half: absence of information, not zero.
  - **The withholding rule is untouched**: an undeclared period still reports
    no figure at all. A split describes money already paid; it is not an
    estimate.

  Regression tests: `test_payment_ledger.py::TestCapitalInterestSplit` (both
  halves · penny mismatch rejected · one half completes the other · negatives
  · None-not-zero totals · sensor split and total) plus the service round trip
  — 289 → 298.

- **2026-10-22 (later) — a projection line, quoted from the board's own
  equivalence.** *Qualifies the withholding rule rather than reversing it.*
  The board's Feb 2025 → Jun 2026 announcement published its own annual
  equivalent in words: *"…21 pence per-watt for the 17 month period. This is
  equivalent to a 12 month savings payment of …15p per watt."* A per-year
  projection at **that** rate is therefore a quotation, not the accrual the
  no-accrual rule (2026-10-08) forbids — the difference is whose number it is.

  - **Inputs**: `annual_rate_p_per_w` and `lifespan_years` (1–200), stored with
    the ledger and set through the new `kirkhill_wind.set_projection` service
    (JSON null clears either). Nothing is defaulted into existence: the member
    types the board's rate (15) and the lifespan (25).
  - **The line** reads *"Projection only — 15.00 p/W per year on your watts is
    about £383.92/year and £9,598.00 over 25 years, if that rate held. Not a
    board figure."* — italic, caveated, and **counted by nothing**: it fills no
    period, adds to no total and changes no ROI. Withheld periods stay
    withheld; a projection is not an estimate of what is owed.
  - **Capacity** comes from the latest record, so the projection tracks the
    watts the member actually holds.

  Regression tests: `TestProjection` (arithmetic · any missing input reads
  None · stored and cleared · bad inputs refused · sensor projection from
  latest capacity · never leaks into totals) plus the service round trip —
  298 → 310.

- **2026-10-22 (later) — board figures arrive through a shipped YAML file.**
  The API has no payment endpoints today (the request for *financial figures
  owned by the API* is already queued — see `docs/api.md`), Ethex exposes
  portfolio values rather than dated payments, and board announcements are
  published as prose. So the repository itself becomes the source: a shipped
  `board_announcements.yaml` inside the integration, upserted into the ledger
  as `source: board` on every setup.

  - **On by default, switchable.** Options → *Board figures source* offers
    `Repo file — board_announcements.yaml` (default) and `Manual entry only`;
    manual skips the file completely and leaves the card the only writer.
    Moving to manual does not remove figures the file already brought in, and
    moving back re-applies it.
  - **Edit it in a PR → git is the audit trail** of who entered which figure
    and when, and `kirkhill_wind.reload_integration` (or a restart) applies it
    — no code deploy, unlike every other change to this component.
  - **Matched by period**: same period in, same record out — rate, dates,
    `announced_on` and note updated while the watts and any capital/interest
    split already entered against it are kept. Periods the file does not name
    are never touched, so card-entered records cannot be overwritten.
  - **Capacity comes from the API** for a new period (the board announces a
    rate, not your watts); with no capacity available the record is skipped
    with a warning rather than guessed — a rate without watts cannot produce a
    figure.
  - **The board's figure wins, never silently over a split**: a re-announced
    rate that cannot coexist with an entered capital/interest pair clears the
    pair and logs it.
  - Ships **empty, with a commented example**: a shipped announcement must not
    overwrite figures already entered in the card until the maintainer adds
    entries.

  Regression tests: `TestBoardAnnouncements` (creates · user records untouched
  · same period updates in place and keeps its watts · rate change clears an
  incompatible split · empty is a no-op with no write · missing capacity
  skipped · malformed entries skipped · applied during setup) — 310 → 318.

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

- **2026-10-22 (later) — `main` is at `4.18.2`, published as a pre-release;
  `4.18.1` is the latest stable (promoted earlier the same day on the owner's
  testing) and `4.18.0` remains a superseded pre-release for reference.**
  Nothing is deployed by
  releasing: files reach this host only when `origin/main` is mirrored into
  `/homeassistant/custom_components/kirkhill_wind/`, and Python changes need
  Home Assistant fully restarted — the owner's explicit go-ahead. Frontend-only
  changes are a copy plus a browser refresh. Production runs the same code as
  `main`; its manifest reads the new version at the next restart.
  `CHANGELOG.md` is the authoritative version history. GitHub Releases/HACS are
  for other users; this host deploys from `origin/main` commits mirrored into
  `/homeassistant/custom_components/kirkhill_wind/`.

[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
