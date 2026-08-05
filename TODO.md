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
