# To-do list

## Release roll-out — SCADA v4.8.x

- [x] Update README.md and info.md for the SCADA tab, panel view, and per-turbine sensors
- [ ] Update production HA instance to v4.8.4 via HACS
- [ ] Restart Home Assistant on production
- [ ] Verify the SCADA tab is present, is the first tab, and fills the whole panel
- [ ] Verify `sensor.turbine_t1_generation_today` (and per-turbine generation/rotor sensors) now exist
- [ ] Confirm the KPI cards render as entity cards (no stat-card config errors)
- [ ] Confirm `sensor.kirk_hill_wind_farm_generation_today_site` exists (used by the SCADA card's grid energy)

## Backlog

- [ ] Create a `SUPPORT` file (GitHub auto-features it in the repo file list)
- [ ] Create a `CONTRIBUTING` file (GitHub auto-features it in the repo file list)
- [ ] External review #1 — submit to the official HACS default repository so users can find the integration in the HA UI without pasting a URL
- [ ] External review #4 — add a platform-agnostic notification option (generic service/blueprint). Preference is WhatsApp, but design so other users can route to Telegram, Signal, or the HA Companion app.
- [ ] External review #3.2 — investigate the two bare `except Exception` guards (`__init__.py:205` dashboard load, `config_flow.py:151` API-key validate) and confirm they cannot mask a `ConfigEntryAuthFailed`-worthy error as a generic "unknown" failure
- [ ] External review #3.4 — `url_already_exists` is matched by exception message string (`__init__.py:178`); look into more robust error handling in case HA rewords the message
- [ ] External review #3.5 — split the ~700-line dashboard generation/merge logic out of `__init__.py` (1,025 lines) into a dedicated `dashboard.py` module, leaving setup/unload/listeners in `__init__.py`
