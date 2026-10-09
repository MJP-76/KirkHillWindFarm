# The Kirk Hill API

!!! warning "Upstream, and not under our control"

    Every live figure this integration shows comes from the Kirk Hill
    dashboard API — a separate service, developed and deployed by the co-op
    dashboard team, not by us. It has already changed under us more than once.
    When it changes, entities here can appear, change value, or stop
    reporting, usually without notice. This page is the standing record of
    what the API contains, what has changed, and what each change did to the
    entities you may be relying on.

## The API at a glance

| | |
|---|---|
| Base URL | `https://dashboard.kirkhillcoop.org` |
| Style | Read-only REST, JSON. There are no write endpoints |
| Auth | `Authorization: Bearer <kh_live_…>` — an API key issued against a dashboard account |
| Scopes | `owner` (your share, the default) and `site` (whole farm). A key may be restricted to either scope or both; a key limited to one scope **rejects** a request for the other |
| Rate limit | 120 requests per minute per account, shared across all of the account's keys. Exceeding it returns `429` with a `Retry-After` header in seconds. Per-account limits can be raised by an administrator |
| Timestamps | UTC ISO-8601. Named ranges use `Europe/London` local day boundaries |
| Published spec | [`openapi.yaml` at the repository root](https://github.com/MJP-76/KirkHillWindFarm/blob/main/openapi.yaml), copied from the dashboard's own `/api-docs/openapi.yaml` |

Other responses the API can return:

- `401` — missing, invalid, revoked, or inactive key. A key expires after
  **90 days of inactivity** and must be reactivated in the dashboard account
  settings.
- `403` — the key may not read the requested scope. **The published spec does
  not document this response**, but the API returns it, and the integration
  treats it as a permission problem rather than a dead key (v4.14.1).
- `422` — invalid `range` or timestamp parameters.
- `423` — the dashboard password must be changed before API keys work.

## Endpoints

| Endpoint | Parameters | Returns | Polled by us? |
|---|---|---|---|
| `/api/v1/current` | `scope` | Latest 1-minute power and wind readings, turbine state text, capacity factor, `capacity_watts` | **Yes — every poll**, once per scope |
| `/api/v1/summary` | `range`, `scope`, `from`, `to` | Generation totals, capacity factor, turbine counts, `latest_import_status` for a window | **Yes —** `range=today` every poll, the rest hourly, once per scope |
| `/api/v1/turbines` | `range`, `scope`, `from`, `to` | Per-turbine generation, capacity factor, coordinates, rotor speed | **Yes — every 10 minutes**, `range=today` and `range=all`, site scope |
| `/api/v1/wind-speed` | `range`, `scope`, `from`, `to` | Mean wind speed time series | **No** — dropped in v4.13.1; `/current` already carries wind speed, and HA's recorder holds the history |
| `/api/v1/generation` | `range`, `scope`, `from`, `to` | Bucketed kWh generation series | **No** — in the spec since it was first committed, but its stability has never been confirmed (see [API feature requests](api-feature-requests.md)) |
| `/api/v1/carbon-avoided` | `range`, `scope`, `from`, `to` | Indicative CO₂ avoided, weighted by NESO grid carbon intensity | **No** — appeared upstream on 2026-10-08 (see below) |

The wind speed and forecast figures on the dashboard are **not** from this
API: the forecast sensors come from Open-Meteo, a separate public service.

### Query parameters

**`range`** — `today`, `yesterday`, `7d`, `30d`, `ytd`, `all`, `custom`
(with `from`/`to` as ISO-8601 timestamps), or a four-digit year from 2024 to
the current dashboard year (for example `2024`). Default is `7d`. The current
year behaves as year-to-date; completed years cover the full UK-local calendar
year. The integration maps its timeframes as `yesterday → yesterday`,
`today → today`, `week → 7d`, `month → 30d`, `ytd → ytd`, `year → <YYYY>`,
`alltime → all`.

**`scope`** — `owner` (default) or `site`. Wind speed, capacity factor and
turbine active/inactive state are physical readings and do **not** change with
`scope`; generation, power and money-adjacent figures do.

On `/api/v1/turbines` the spec advertises the full `range` set, but in
practice only `today` and `all` are known to work — intermediate ranges are
the subject of [feature request 1](api-feature-requests.md).

## How often we poll

At the default 60-second scan interval, tiered so the call count stays far
below the 120/minute limit:

| Tier | Interval | Calls |
|---|---|---|
| Fast | every poll | `/current` × 2 scopes, `/summary?range=today` × 2 scopes |
| Medium | every 10 minutes | `/turbines?range=today`, `/turbines?range=all` |
| Slow | hourly | `/summary` for yesterday, week, month, ytd, year, `year_YYYY`, alltime — × 2 scopes |

Completed calendar years are fetched once and cached forever, so the slow
tier shrinks as time passes. The exact counts are pinned by
`tests/test_coordinator.py::TestApiCallBudget`, because a doubled summary
fetch once shipped unnoticed (v4.13.4).

## Change history

`openapi.yaml` is committed at the repo root, so the diffs below are the
record. Dates are when we noticed and captured the change, not necessarily
when it shipped upstream.

| Date | Spec release | What changed |
|---|---|---|
| 2026-07-03 | first commit | Six endpoints: `current`, `summary`, `generation`, `wind-speed`, `turbines`. **Note `carbon-avoided` was not there** — and the spec's `Range` parameter already advertised `custom` and four-digit years |
| 2026-10-04 | reconciled against the live API | **`site_capacity_watts` removed** from `CurrentSummary` and `Summary`, replaced by `capacity_watts` + `capacity_kw`. **`latest_import_status` enum changed from `completed` to `success`/`running`.** Added `total_power_watts`, `total_generation_kwh_today`, `total_generation_wh_today` to `CurrentSummary`; added the capacity pair to `CurrentTurbine`; added seven `co2_avoided_*` fields plus `latest_carbon_intensity_at` to `Summary` |
| 2026-10-08 | `20261008T151851Z-ce4aaa47b8cd` | **`GET /api/v1/carbon-avoided` added**, with `CarbonAvoidedSummary`/`Point`/`Response` schemas. **`429` responses documented on every endpoint**, with `Retry-After`. The `Turbine` capacity pair confirmed |

Two things worth stating plainly, because they are the shape of the risk:

- **Nothing has been deleted from the API's endpoint set.** Every removal so
  far has been at field or value level, which is harder to notice: an endpoint
  that vanishes breaks loudly, a field that vanishes leaves a sensor reading
  `unknown`.
- **The spec and the API are separate documents and have disagreed.**
  `site_capacity_watts` was *required* by the spec from the first commit
  onwards, yet the API **never sent it** — that was only discovered when the
  spec was reconciled against a real payload in v4.13.7. A green contract test
  proves the fixtures match the spec, not that the API matches either.

## What this did to the entities

### Added

| Entity | API change behind it | Version |
|---|---|---|
| `Generation (2025)`, `Generation (2024)` (owner + site) | four-digit `range=YYYY` support | v4.11.5 |
| `Data complete`, `Data generated at`, `Unknown turbines`, `Latest import status`, rotor `sampled_at` attribute | fields the API already sent and we were discarding — no upstream change needed | v4.13.1 |
| `Owner share %` derived live from `capacity_watts` | the summary capacity pair | v4.8.66 |
| `Member savings value` + `Owner rate (p/W)` | owner `capacity_watts` on `/current` | v4.15.0 |

### Changed value

- **`Latest import status`** used to read `completed`; the enum is now
  `success` / `running`, where `running` means the window is still being
  backfilled. Any automation matching on the old literal stopped matching
  silently — nothing about the entity itself changed, only what it reports.
- **Capacity fields** moved from the single `site_capacity_watts` to
  `capacity_watts` + `capacity_kw`, scoped to whatever the key reads.

### Removed

- **`Site Total Capacity`** — read `site_capacity_watts`. Dropped in the
  2026-07-02 sensor refactor, and confirmed the right call in v4.13.7 when the
  API turned out never to have sent that field at all (it would have read
  empty). Its replacement is the `capacity_watts` read that feeds
  `Owner share %` and `Member savings value`.
- **No entity has yet been removed because upstream deleted a field it was
  using.** That is the untested case, not an impossible one.

### If upstream removes something we depend on

The failure mode is quiet: `_parse_data()` guarantees an envelope, not a
field, so a vanished key surfaces as an `unknown` sensor (or a defaulted `0`)
rather than an error. When that happens the fix is a release, not a
configuration change — check [the changelog](changelog.md) for the version
that names it.

## How we catch upstream changes

- **`OpenAPI sync`** ([`.github/workflows/openapi-sync.yml`](https://github.com/MJP-76/KirkHillWindFarm/blob/main/.github/workflows/openapi-sync.yml))
  runs daily at 06:23 UTC. It reads the dashboard's build stamp
  (`data-release-id`) from `/api-docs`, and only when that stamp moves does it
  download the spec and compare it *parsed* against our copy.
- If the content differs it refreshes `openapi.yaml`, records the release in
  `.github/openapi-release-id`, and opens or updates a single long-lived PR on
  the `chore/openapi-sync` branch listing **new endpoints, new schemas, new
  fields, dropped fields and changed `required` lists** — `scripts/openapi_check.py`
  does the diffing.
- The same PR runs `tests/test_openapi_contract.py` against the refreshed
  spec, so a break is reported in the PR body even though the PR is still
  opened. That separation is deliberate: an upstream change that breaks our
  fixtures must still surface.
- The first sync caught `carbon-avoided`, the `429` responses and the `Turbine`
  capacity pair.

**What this does not cover:** a behaviour change with no spec change. The
spec said `site_capacity_watts` was required for three months while the API
never sent it. The contract test is a floor, not a guarantee.

## What we have asked upstream for

See [API feature requests](api-feature-requests.md) for the two open requests
(intermediate ranges on `/turbines`, a structured curtailment reason) and
`TODO.md` #55 for the rest of the queue — combined endpoints, `range=custom`
stability, rate-limit documentation, and financial figures owned by the API.
