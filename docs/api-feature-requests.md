# API Feature Requests

## Issue 1: Per-turbine generation for intermediate ranges

**Title:** Support intermediate ranges (7d, 30d, ytd, year) on `/api/v1/turbines`

**Labels:** enhancement

---

Currently `/api/v1/turbines` only supports `range=today` and `range=all`. We'd like intermediate ranges (`7d`, `30d`, `ytd`, `year`) to be supported on this endpoint, matching what `/api/v1/summary` already offers.

### Why we want this

The Home Assistant integration already renders per-turbine history charts in each turbine's detail modal (power, wind speed, capacity factor, rotor speed, generation today). The chart infrastructure supports arbitrary timeframes (6H through 1Y) and switches between HA's raw history API and hourly recorder statistics depending on window length.

However, the "Generation Today" chart is limited to today's accumulation curve because the sensor resets at midnight. There is no way to chart per-turbine generation over a week, month, or year — only today's running total or the all-time lifetime figure.

If `/api/v1/turbines` accepted `range=7d`, `30d`, `ytd`, and `year` (with the same `scope` parameter), we could expose per-turbine generation sensors for each timeframe (mirroring the 7 farm-level generation sensors we already create from `/api/v1/summary`). These would feed directly into the existing chart infrastructure with no frontend changes needed.

### What it would enable

- Per-turbine generation comparison charts (this week, this month, YTD)
- Identifying underperforming turbines over meaningful periods, not just today
- Per-turbine generation share trends over time
- Consistency with the farm-level summary endpoint which already supports all these ranges

### Suggested response shape

The existing `Turbine` object already has `generation_kwh`, `generation_share_percent`, and `capacity_factor_percent` — the same fields for intermediate ranges would be sufficient. No new fields needed.

---

## Issue 2: Curtailment reason in turbine state data

**Title:** Expose curtailment reason (grid constraint, environmental, maintenance) in turbine state

**Labels:** enhancement

---

The integration currently detects curtailment by mapping the ENERCON `state_text` string `"Turbine stopped: SCADA (bird and bat protection)"` to a `curtailed` category. This works, but all curtailment looks the same — we can't distinguish between:

- **Environmental curtailment** (bird and bat protection — what we detect today)
- **Grid constraint curtailment** (export limitation, frequency response, balancing mechanism)
- **Maintenance window curtailment** (planned outage, scheduled service)
- **Commercial curtailment** (negative pricing, contract-based dispatch down)

### Why we want this

The Home Assistant integration surfaces turbine status in a SCADA-style dashboard with per-turbine state pills and a farm alarm binary sensor. Users (co-op members) are interested in *why* their turbines aren't generating, not just *that* they aren't. Distinguishing "the grid can't take the power right now" from "bats are flying" from "the turbine is broken" is materially different for member understanding and trust.

If the API exposed a structured curtailment reason — either as a new field alongside `state_text` (e.g. `curtailment_reason: "environmental" | "grid" | "maintenance" | "commercial" | null`) or as additional state_text variants we could map — the integration would display this in the turbine status card and could trigger different notification routes (e.g. grid constraint = informational, fault = urgent).

### What it would enable

- Different alarm/notification priorities by curtailment type
- Dashboard display showing *why* a turbine is curtailed, not just that it is
- Historical analysis of curtailment breakdown (how much generation was lost to grid constraints vs environmental vs faults)
- Better member communication about farm performance

### Suggested response shape

Either:
- A new `curtailment_reason` field on `CurrentTurbine` (string enum, null when not curtailed), or
- Distinct `state_text` values for each curtailment type that we can map in `TURBINE_STATUS_MAP`

Either approach works — a dedicated field is cleaner but new state_text values are backwards-compatible.
