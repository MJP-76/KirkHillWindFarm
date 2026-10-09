# Code review brief — Kirk Hill Wind Farm HA integration

Give the repository a **design-focused** review. CI already passes (ruff, HACS
validation, Hassfest, version-sync); you are NOT reviewing for "does it pass CI".
Focus on correctness, robustness, and design with these specific questions below.

Repo: https://github.com/MJP-76/KirkHillWindFarm (branch `main`, v4.16.3)
Start here: `custom_components/kirkhill_wind/`, then `AGENTS.md`, then
`docs/development/decisions.md` (read the decisions doc — it records why the
code is shaped this way and answers several questions below already).

## Context
- Tiny custom integration: one coordinator polling a wind-farm API, farm-level +
  per-turbine sensors/binary_sensors, a bundled JS SCADA card, and dashboard
  generation/merge code in `dashboard.py` (`__init__.py` is setup/unload plus
  `async_migrate_entry`, 266 lines).
- `via_device_id` replaced the deprecated `via_device=(DOMAIN, entry.entry_id)`
  tuple (HA Core 2027.8 compat). The hub device id is resolved once in
  `__init__.py::async_setup_entry` and stored on the coordinator. Highest-risk
  recent change.

## Already reviewed / resolved — do NOT re-raise
These were raised in earlier external reviews and are deliberately settled.
Treat them as closed; flag only if you find a new, concrete problem:

- **HACS default-repository inclusion** — on the maintainer's `TODO.md`.
  Recommend at most once; do not treat as a defect.
- **Energy Dashboard compatibility (state_class `total_increasing`)** — a
  recorded decision: the farm's energy is sold to the grid/co-op, not
  self-consumed, so the generation sensors are deliberately NOT wired to the
  native HA Energy dashboard. Window-total sensors (today/week/month/YTD) stay
  `state_class=total`; only `alltime` is `total_increasing`. Do not suggest
  reclassifying them.
- **OptionsFlow / editing options post-setup** — already implemented: the
  integration exposes a full options flow (`KirkHillWindOptionsFlow` in
  `config_flow.py`) covering polling interval, the dashboard toggle, and the
  payment-tracking toggle. Users can edit all of these from the integration
  entry's Options button without re-adding. The legacy `owner_share_percent` /
  `owner_value_rate` / `graph_hours` options were removed (share is now derived
  from the API capacity ratio). Projected annual earnings options were removed
  in v4.11.7.
- **Monetary sensors / currency** — recorded decision: monetary sensors keep
  `device_class=MONETORY` with a hardcoded unit `"GBP"` (do not pull the
  system/locale currency).
- **"Completed years are cached forever, so historical £ data could go stale."**
  Not applicable. `sensor.py` returns `None` for `alltime` and every `year_*`
  timeframe, so no £ value is ever derived from a cached year — only generation
  kWh is. See `docs/development/decisions.md`.
- **"Remove `RestoreEntity` so `ConfigEntry.options` is the sole authority."**
  **Settled in v4.13.6 — do not raise again.** Removal as originally specified was
  a data-loss regression: prices set before v4.13.0 were never written to options and
  live only in `restore_state`. That has been fixed properly — the restore read is now a
  **one-shot backfill** gated on a `CONF_PRICE_RESTORE_PENDING` marker that the v9
  migration writes, so options is the sole authority in steady state *and* no
  pre-existing price is lost. Details and the three easy-to-break design points are in
  `docs/development/decisions.md`; regression tests are
  `test_number.py::TestPriceBackfillUpgrade` and
  `test_init.py::TestPriceBackfillMigration`.
- **"Split the coordinator."** Agreed in principle, deliberately deferred until
  the API-call-budget test exists — which it now does (`TestApiCallBudget`,
  v4.13.5). The recorded blocker is cleared, but the split itself is still
  deferred, so do not raise it as a defect.
- **"Assert on sets of API calls in coordinator tests."** Do not suggest
  reverting to set-based assertions — a set is invariant under duplication,
  which is how a doubled summary fetch shipped. See below.

## Specific review questions

### 1. Device registry / via_device_id
- `device.py::get_farm_device_id` uses `registry.async_get_or_create` with
  `entry_type=SERVICE`. Is `SERVICE` the right entry type for a hub here, and do
  farm-level entities correctly attach to the same device?
- The hub id is resolved once per setup in `__init__.py::async_setup_entry`
  before platform setups are forwarded, and stored on the coordinator. Any
  race/ordering edge cases for platforms that read it?
- Is calling `async_get`/`async_get_or_create` safe here (context, locking)?
- Any downstream HA version where `via_device_id` might not be supported yet?

### 2. Coordinator robustness
- `coordinator.py`: how are API errors / timeouts handled? Is there a backoff?
- `entity.py::_owner_share_pct` auto-derives owner share from generation ratio
  when unset. Sound logic? Numeric edge cases (site > 0 check, rounding)?

### 3. Sensor correctness
- `sensor.py`: units conversion for site vs owner power (MW vs kW), the
  `_display_energy_from_kwh` scale thresholds, and the generation sensors —
  any off-by-one or unit-scale bugs?
- The alltime/past-year `None` suppression is deliberate; do not report it as a
  missing value.

### 4. Dashboard generation code in `dashboard.py`
- Dashboard create/merge/reset now lives in `dashboard.py` (531 lines), split
  out of `__init__.py` in v4.13.0. Public surface: `build_dashboard_config`,
  `merge_dashboard_config`, `card_match_key`, `OBSOLETE_CARD_KEYS`.
- Dead code was removed across several releases (owner/site_value_entities,
  kpi_cards, `Projected annual earnings` entities, `_deprecation_banner`). Are
  the remaining list-building blocks still consistent, or is there more
  dead/duplicated structure an AI or maintainer could trip over?

### 5. Anything else a maintainer should know
- SECURITY: secrets handling, HTTPS, no hardcoded credentials. Note the API key
  lives in `entry.data`; `diagnostics.py` must redact it.
- TYPING / portability: `from __future__ import annotations`, py311 target.
- Any obviously fragile string-keyed data access (`coordinator.data[...]`).
- **Do not** suggest reverting `_parse_data`'s dict guarantee or bypassing
  `merge_options` when writing options — both are enforced invariants with
  regression tests.

## Output format
Give a numbered list of findings, each with: severity (blocker / major / minor /
nit), the file:line, what the risk is, and a concrete suggested fix. End with a
short "what I'd do next" recommendation. Do NOT edit any files — this is
read-only review.
