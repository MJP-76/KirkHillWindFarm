# Kirk Hill Wind Farm

Home Assistant custom integration for the Kirk Hill Community Wind Farm.

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

Connects to the Kirk Hill dashboard API using your personal API key and provides live sensors for the whole farm and each individual turbine.

## Project notes

Owner/site generation kWh values are **live dynamic API values**. Owner/site financial earnings shown in the dashboard are **projected values** and **not real-time dynamic earnings**. All-time projected value now uses the API all-time timeframe start date when available.
Kirk Hill API remains the authoritative source for actual generation values. Open-Meteo integration is forecast-only and does not require a separate forecast API key.
Dev updates can be published as GitHub pre-releases for early testing while stable releases remain marked as Latest.
Stable release flow uses a full merge into `main` before final tagging/publishing.
Dashboard layout and labels are being aligned to the live Kirk Hill dashboard UX from exported snapshots, while preserving Home Assistant-native entity behavior.

The Kirk Hill documents (agreement/rules/share offer) help define the finance model structure and assumptions, but they do not provide full live values on their own. Live API/dashboard data and the latest published accounts are still required for current figures.

### Latest AGM finance notes

- 2025 generation was below expectation due to low winds; 2026 performance to date has been more encouraging.
- CfR has run the Coop as Managed Service Agent for the last six months.
- Updated model projects a 2026 member savings payment (including 2025 catch-up) of around **GBP250 per GBP1,713 shares** (~1,000W).
- Long-term average projected member savings is around **GBP132/year per GBP1,713 invested** (vs share offer projection of GBP125/year).
- Savings payments are intended to be made **twice yearly** (August and February).
- First member savings payment is expected in **autumn 2026** (likely October), subject to Ethex registration progress.
- 2025 audited accounts were presented at the AGM.
- Local community funds (North Carrick CBC and Dailly CDT) continue to receive support from Kirk Hill wind farm funds.
- New live generation dashboard launched: `dashboard.kirkhillcoop.org`.

## What you get

- **Farm sensors** — live power, capacity factor, wind speed, active/inactive turbine count, and alarm state
- **Generation sensors** — yesterday, today, week, month, year-to-date, year, and all-time totals for both your owner share and the whole site
  - Dashboard display auto-scales generation units from kWh up to EWh for large values
- **Owner + site projected value sensors** — estimated GBP value for each timeframe from configured annual projections (non-dynamic)
- **Projected finance inputs** — configurable annual owner/site projected earnings values used by projected finance sensors
- **AGM/published-books manual finance inputs removed** — owner/site projected figures remain available
- **Open-Meteo forecast sensors** — optional next-hour / 3h / 24h wind-speed forecast context (non-authoritative), using automatic farm-location lookup
- **Optional experimental Ethex onboarding toggle** — config-flow option to also configure payment tracking via `ha-ethex`
- **Per-turbine sensors** — power (owner + site), capacity factor (owner + site), wind speed, state text, active binary sensor, generation today (site), generation all-time (site), and rotor speed for each of the 8 turbines
- **SCADA tab** — the first tab on the auto-generated dashboard, a full-bleed animated single-line diagram (turbines → bus → transformer → grid) with live per-turbine power, status, today's generation and rotor speed; national grid block shows Owner and Site export and to-grid-today, with wind/forecast chips and a flashing alarm indicator; panel view so it fills the entire tab
- **Auto-generated Lovelace dashboard** — created automatically during setup with SCADA (first), finances, history, and turbines tabs containing:
  - Taller turbine map viewport so all turbines fit more reliably on-screen
  - Active/inactive turbine count and alarm status (alarm = actual thermal/electrical turbine fault)
  - An **interactive turbine map** showing all 8 turbines with T1–T8 labels, running/stopped legend, hover titles, live spin animation proportional to output, scroll/pinch zoom, drag-to-pan, and double-click to reset
  - Full per-turbine detail cards
- **Bundled chart cards** — ApexCharts and Plotly Lovelace cards shipped with the integration (no separate HACS installs needed)
- **Dual-axis Power chart** — site power (MW) and owner power (kW) on separate Y-axes
- **Power vs Wind scatter plot** — wind speed vs site power correlation
- **Combined Power and Wind history graph** — owner power, site power, and wind speed on a single chart
- **Dashboard customisation preserved** — user-added cards, sections, and views retained across reloads/updates
- **Factory reset** — wipe customisations deliberately only: untick "Create dashboard automatically" in Options and rebuild the tab, or call `kirkhill_wind.reset_dashboard`
- **Reset dashboard service** — `kirkhill_wind.reset_dashboard` restores defaults
- **Finances tab shows generation kWh + earnings** for all timeframes (Owner & Site)
- **Overview tab removed** — dashboard starts with SCADA, then Finances, History, Turbines

## Requirements

- A Kirk Hill Co-op membership with API access
- Your personal Kirk Hill dashboard API key

> **Not affiliated with Kirk Hill Co-op.** This is an independent community integration.
