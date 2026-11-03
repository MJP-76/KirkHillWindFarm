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

---

## Issue 3: Unattended access to the OpenAPI spec

**Title:** Let an automated client read `/api-docs/openapi.yaml`, or publish a changelog feed

**Labels:** enhancement

**Status:** asked upstream — awaiting feedback

---

Since the dashboard's 2026-10-23 release, `/api-docs` and its spec require a signed-in session: an anonymous request is redirected to the home page, and a request without a session answers `401 {"message": "Please sign in to view API documentation."}`.

### Why we want this

The integration ships a scheduled job (`OpenAPI sync`, daily at 06:23 UTC) that reads the build stamp `data-release-id` from the dashboard home page and, only when that stamp moves, downloads `/api-docs/openapi.yaml` and compares it *parsed* against the copy committed in the repository. When the content differs it refreshes the spec, records the release, and opens a PR listing the new endpoints and schemas.

**The trigger still works** — `data-release-id` remains public on `/` — so the job knows exactly when upstream ships. It fails only at the **download**, which is now gated. That has left the committed spec three weeks behind (recorded `20261008T151851Z-ce4aaa47b8cd`, live `20261029T001606Z-5be915ce91ed`), and more importantly means code can be written against an endpoint the committed spec does not document — which is precisely the drift the job exists to catch. Two endpoints are already in that state.

The fallback we implemented is a member's dashboard credentials held as CI secrets and driven through `POST /dashboard-api/login` with an `X-XSRF-TOKEN` cookie. It works, but it is fragile in ways a token would not be: two-factor authentication cannot be supplied by CI, repeated failed attempts are temporarily locked upstream, and a password rotation silently breaks the job.

### What it would enable

- A spec that stays in step with the API it describes, with no human in the loop
- The contract test that pins our fixtures to the spec to keep running (it currently skips for the missing endpoint)
- Drift detection for endpoints added after 2026-10-23
- No shared password sitting in CI

### What we would need

Either:

1. **A token that unlocks the spec** — an API key presented as `Authorization: Bearer …`, or a dedicated read token, permitting `GET /api-docs/openapi.yaml` and ideally `/api-docs/changelog.md` too. A *dummy* `kh_live_*` key is rejected by the gate today; whether a *valid* key is accepted has not been tested.
2. **A changelog feed** — RSS, Atom or JSON, covering `/api-docs/changelog.md`. This would not unblock the spec download, but it would let a client detect upstream changes with no credentials at all.

Either is sufficient on its own: (1) solves the sync outright, (2) is a useful addition on top of it. There is currently no feed at any obvious path — the docs page, the spec and the Postman collection contain no `rss`, `atom`, `feed` or `webhook` reference.
