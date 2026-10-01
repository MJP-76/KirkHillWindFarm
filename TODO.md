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
- [ ] Remove the deprecated turbine map card (`kirkhill-wind-turbine-map`) entirely — currently bundled with a deprecation banner since v4.8.81

## Code review backlog

- [ ] Fetch the Open-Meteo forecast in parallel with the medium-tier turbine fetches (currently sequential because the forecast location derives from the freshly fetched turbine map; would need to fall back to last-known coordinates to parallelise)
- [ ] Investigate the two bare `except Exception` guards (`__init__.py:205` dashboard load, `config_flow.py:151` API-key validate) and confirm they cannot mask a `ConfigEntryAuthFailed`-worthy error as a generic "unknown" failure
- [ ] `url_already_exists` is matched by exception message string (`__init__.py:178`); look into more robust error handling in case HA rewords the message
- [ ] Split the ~700-line dashboard generation/merge logic out of `__init__.py` (1,025 lines) into a dedicated `dashboard.py` module, leaving setup/unload/listeners in `__init__.py`
- [ ] Add a platform-agnostic notification option (generic service/blueprint). Preference is WhatsApp, but design so other users can route to Telegram, Signal, or the HA Companion app

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