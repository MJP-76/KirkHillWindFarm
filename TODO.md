# To-do list

## Release roll-out — SCADA v4.10.0

- [x] National Grid detail modal with historical data and timeframe selector
- [x] Grid labels renamed: Export → Current Export, To Grid Today → Today To Grid
- [x] Consistent colour scheme: amber=power/energy, cyan=wind, green=financial, primary=titles
- [x] Turbine box layout: capacity first, status pill spacing fixed
- [x] Font styling consistency with Owner/Site cards
- [x] Energy chart reset filtering (no trailing 0s on 1m/6m/1y)
- [x] Font scaling fixes (VIEWBOX hMin/hMax, fs capped)
- [x] Dashboard fills screen (ha-card height restored)
- [ ] Deploy v4.10.0 to production
- [ ] Restart Home Assistant to load new Python code
- [ ] Verify v4.10.0 in production
- [ ] Create GitHub release v4.10.0 (stable; latest for HACS)

## Release roll-out — SCADA v4.9.0

- [x] Redesign top chip row: Refresh | Version | API | Turbine Status | Wind Speed
- [x] Version pill shows Running/Latest from HACS update entity with amber update-available state
- [x] Turbine status pill: three-tier colors (green/amber/red) based on active count
- [x] API status pill: flash red when down, three-tier ready for rate limiting
- [x] Turbine status pop-out with per-turbine history (last 24h, expandable rows)
- [x] API status pop-out with status history and durations
- [x] Wind Speed chip moved to top row as single line
- [x] All pills use tspan layout — no white space gaps at any width
- [x] Legend removed (status colors self-explanatory)
- [x] Card height locked to1300px to eliminate bottom white space
- [x] Generation panels repositioned under pill line
- [x] Grid box aligned with bus bar bottom
- [x] Turbine map placeholder to prevent stale module crash
- [x] Deploy v4.9.0 to production
- [x] Restart Home Assistant to load new Python code
- [x] Verify v4.9.0 in production
- [x] Create GitHub release v4.9.0 (stable; latest for HACS)
- [x] Remove turbine map placeholder file after HA restart (stale module refreshed)
- [ ] Rate limiting: expose `rate_limited` attribute on API status entity when API supports 429
- [x] Font sizing: investigate why fonts render smaller than expected on some instances (theme variables vs fallbacks, --khscada-fs scaling interaction)
- [x] Dead white space: eliminate bottom white space below generation panels / grid box — panels should fill the card height dynamically

## Release roll-out — SCADA v4.8.x

- [x] Update README.md and info.md for the SCADA tab, panel view, and per-turbine sensors
- [x] Deploy v4.8.74 to production (turbine Generation Today chart, 24h timeframe reset, scatter decimals, waiting indicator)
- [x] Deploy v4.8.75 to production (API Status pill on SCADA card backed by `binary_sensor.<farm>_api_status`)
- [x] Restart Home Assistant on production to pick up the new binary_sensor platform code
- [x] Verify `binary_sensor.kirk_hill_wind_farm_api_status` exists and is `on` (API reachable)
- [x] Verify the SCADA card config has `api_status_entity` merged in
- [x] Create GitHub releases v4.8.74 and v4.8.75 (stable)
- [x] Deploy v4.8.76 to production (map tile fallback to CARTO Voyager, turbine activity history chart, SCADA bottom chrome row)
- [x] Deploy v4.8.77 to production (deprecation banners on Finances/Turbines, History tab removed, Turbines tab trimmed, graph_hours option removed)
- [x] Create GitHub release v4.8.77 (stable; includes 4.8.76)
- [x] Fix issue #47 follow-ups in v4.8.78 (stuck waiting overlay, themed chart tooltips, 6M/1Y hourly stats)
- [x] Reply to issue #47 (4.8.74/4.8.75 fixes, by-design chart types, request dashboard dump + map console output)
- [x] Post follow-up to issue #47 (dashboard untick/tick reset, API pill clarifications, map blocking + deprecation note, planned features)
- [x] Switch turbine map tile source to CARTO Voyager (bypasses tile.openstreetmap.org blocking for embedded apps)
- [x] Deploy v4.8.79 to production (OSM tile revert, SCADA chrome row order, status-since contrast, £ earnings column in Generation & Capacity panels, Finances tab retired and merged into SCADA)
- [x] Restart Home Assistant (via hab `system restart`) to load the v4.8.79 Python code
- [x] Verify v4.8.79 in production (manifest 4.8.79, backend/frontend identical to repo, `value_entity` merged into SCADA card, Finances view pruned)
- [x] Deploy v4.8.80 to production (Turbines tab deleted, Google Maps link in turbine modal, tab renamed "Kirk Hill SCADA", column spacing/14px fonts, negotiated CFD price number entity `number.<farm>_negotiated_price_gbp_mwh`)
- [x] Restart Home Assistant (via hab `system restart`) to load v4.8.80 Python code
- [x] Verify v4.8.80 in production (integration `loaded`, sensors returning real values, negotiated-price entity present)
- [x] Create GitHub release v4.8.80 (stable; latest for HACS) — v4.8.79 changes are included in it, so no separate v4.8.79 release is needed
- [x] Confirm `sensor.kirk_hill_wind_farm_generation_today_2` (site-scope today generation) exists and feeds the SCADA card's grid energy (live value verified)
- [x] Deprecate the turbine map card — standalone `kirkhill-wind-turbine-map` card now shows a theme-aware deprecation banner pointing to the SCADA card; file and card registration stay for now, removal planned for a future release
- [x] Deploy v4.8.81 to production (bundles the deprecated-map-card banner with the API resilience hardening below, all uncommitted in the working tree)
- [x] Restart Home Assistant (via hab `system restart`) to load the v4.8.81 Python code
- [x] Verify v4.8.81 in production (manifest 4.8.81, map card shows banner, hardened polling behaves)
  - Confirmed live: manifest 4.8.81, `data_stale` attribute present on `sensor.kirk_hill_wind_farm_power_site` (hardened coordinator), all backend files identical to repo. A newer SCADA card JS than the working tree was found in production (Wind Speed detail modal, trailing-zero number stripping, panel re-alignment) — synced back so repo == production.
- [x] Create GitHub release v4.8.81 (stable; latest for HACS)

## External review #5 — API resilience hardening (post-v4.8.80 code review)

- [x] Use HA's shared aiohttp session (`async_get_clientsession`) instead of a fresh `ClientSession` + connection pool per poll (coordinator and config-flow API-key validation)
- [x] Make the fast-path `current` fetch failure-tolerant per scope — keep last-known-good data and mark stale instead of blanking the whole tick; 401s still raise `ConfigEntryAuthFailed` so re-auth is prompted
- [x] `gather` the independent turbine ("today" / "all") fetches and make a turbine failure non-fatal (keep last-known turbine map/generation)
- [x] Prime the wind-speed series on tick 1 (it was previously skipped on the first refresh)
- [x] Add a `_parse_data` envelope guard so a 200-level error body raises `KirkHillApiError` instead of a raw `KeyError`
- [x] Use `dt_util.now()` for the calendar-year range (chosen over `utcnow()` so year bucketing tracks HA's local time; UK/IE share UTC offsets so behaviour is identical), exponential backoff between Open-Meteo retries, deterministic sorted timeframe order
- [x] Reviewer point #5 (missing `CONF_CFD_PRICE_GBP_PER_MWH` import causing a setup NameError) was already fixed by commit `cf92593`, and CI already runs ruff (F401/F821) in `.github/workflows/validate.yml` — the review was against a pre-fix state
- [x] Bump version to 4.8.81 (done as part of the map-card deprecation; deploy/verify items are in the Release roll-out section above)
- [ ] Follow-up to reviewer point #3: fetch the Open-Meteo forecast in parallel with the medium-tier turbine fetches. Currently left sequential because the forecast location derives from the freshly fetched turbine map; would need to fall back to last-known coordinates to parallelise (forecast is non-authoritative, so ordering is safe to relax)

## Backlog

- [ ] Create a `SUPPORT` file (GitHub auto-features it in the repo file list)
- [ ] Create a `CONTRIBUTING` file (GitHub auto-features it in the repo file list)
- [ ] External review #1 — submit to the official HACS default repository so users can find the integration in the HA UI without pasting a URL
- [ ] External review #4 — add a platform-agnostic notification option (generic service/blueprint). Preference is WhatsApp, but design so other users can route to Telegram, Signal, or the HA Companion app.
- [ ] External review #3.2 — investigate the two bare `except Exception` guards (`__init__.py:205` dashboard load, `config_flow.py:151` API-key validate) and confirm they cannot mask a `ConfigEntryAuthFailed`-worthy error as a generic "unknown" failure
- [ ] External review #3.4 — `url_already_exists` is matched by exception message string (`__init__.py:178`); look into more robust error handling in case HA rewords the message
- [ ] External review #3.5 — split the ~700-line dashboard generation/merge logic out of `__init__.py` (1,025 lines) into a dedicated `dashboard.py` module, leaving setup/unload/listeners in `__init__.py`
