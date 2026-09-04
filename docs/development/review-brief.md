# Code review brief — Kirk Hill Wind Farm HA integration

Give the repository a **design-focused** review. CI already passes (ruff, HACS
validation, Hassfest, version-sync); you are NOT reviewing for "does it pass CI".
Focus on correctness, robustness, and design with these specific questions below.

Repo: https://github.com/MJP-76/KirkHillWindFarm (branch `main`, v4.8.65)
Start here: `custom_components/kirkhill_wind/` and `docs/development/decisions.md`
(read the decisions doc first — it records why the code is shaped this way).

## Context
- Tiny custom integration: one coordinator polling a wind-farm API, farm-level +
  per-turbine sensors/binary_sensors, a bundled JS SCADA card, and dashboard
  generation code in `__init__.py`.
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
  `config_flow.py`) covering polling interval, projected annual earnings (owner
  & site), owner share %, value rate, graph hours, dashboard and payment
  toggles. Users can edit all of these from the integration entry's Options
  button without re-adding.
- **Monetary sensors / currency** — recorded decision: monetary sensors keep
  `device_class=MONETARY` with a hardcoded unit `"GBP"` (do not pull the
  system/locale currency).

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
  `_display_energy_from_kwh` scale thresholds, `RestoreEntity` fallback logic in
  `GenerationByTimeframe` and turbine generation sensors — any off-by-one or
  unit-scale bugs?
- `GenerationValueByTimeframeSensor::_projection_factor` (ytd uses day-of-year,
  alltime uses period start) — reasonable?

### 4. Dashboard generation code in `__init__.py`
- Dead code was removed (owner/site_value_entities, kpi_cards). Are the remaining
  list-building blocks (`turbine_map_entities`, `scada_turbines`,
  `financial_kpi_cards`, etc.) still consistent, or is there more dead/duplicated
  structure an AI or maintainer could trip over?

### 5. Anything else a maintainer should know
- SECURITY: secrets handling, HTTPS, no hardcoded credentials.
- TYPING / portability: `from __future__ import annotations`, py311 target.
- Any obviously fragile string-keyed data access (`coordinator.data[...]`).

## Output format
Give a numbered list of findings, each with: severity (blocker / major / minor /
nit), the file:line, what the risk is, and a concrete suggested fix. End with a
short "what I'd do next" recommendation. Do NOT edit any files — this is
read-only review.
