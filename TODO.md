# To-do list

## Release roll-out — SCADA v4.8.x

- [x] Update README.md and info.md for the SCADA tab, panel view, and per-turbine sensors
- [x] Deploy v4.8.74 to production (turbine Generation Today chart, 24h timeframe reset, scatter decimals, waiting indicator)
- [x] Deploy v4.8.75 to production (API Status pill on SCADA card backed by `binary_sensor.<farm>_api_status`)
- [x] Restart Home Assistant on production to pick up the new binary_sensor platform code
- [x] Verify `binary_sensor.kirk_hill_wind_farm_api_status` exists and is `on` (API reachable)
- [x] Verify the SCADA card config has `api_status_entity` merged in
- [x] Create GitHub releases v4.8.74 and v4.8.75 (stable)
- [x] Deploy v4.8.76 to production (map tile fallback to CARTO Voyager, turbine activity history chart, SCADA bottom chrome row)
- [x] Reply to issue #47 (4.8.74/4.8.75 fixes, by-design chart types, request dashboard dump + map console output)
- [x] Post follow-up to issue #47 (dashboard untick/tick reset, API pill clarifications, map blocking + deprecation note, planned features)
- [x] Switch turbine map tile source to CARTO Voyager (bypasses tile.openstreetmap.org blocking for embedded apps)
- [ ] Deprecate the turbine map card (interim fix in place via CARTO; map planned for removal in a future release)
- [ ] Confirm `sensor.kirk_hill_wind_farm_generation_today_site` exists (used by the SCADA card's grid energy)

## Backlog

- [ ] Create a `SUPPORT` file (GitHub auto-features it in the repo file list)
- [ ] Create a `CONTRIBUTING` file (GitHub auto-features it in the repo file list)
- [ ] External review #1 — submit to the official HACS default repository so users can find the integration in the HA UI without pasting a URL
- [ ] External review #4 — add a platform-agnostic notification option (generic service/blueprint). Preference is WhatsApp, but design so other users can route to Telegram, Signal, or the HA Companion app.
- [ ] External review #3.2 — investigate the two bare `except Exception` guards (`__init__.py:205` dashboard load, `config_flow.py:151` API-key validate) and confirm they cannot mask a `ConfigEntryAuthFailed`-worthy error as a generic "unknown" failure
- [ ] External review #3.4 — `url_already_exists` is matched by exception message string (`__init__.py:178`); look into more robust error handling in case HA rewords the message
- [ ] External review #3.5 — split the ~700-line dashboard generation/merge logic out of `__init__.py` (1,025 lines) into a dedicated `dashboard.py` module, leaving setup/unload/listeners in `__init__.py`
