# Kirk Hill Wind Farm

Home Assistant custom integration for the Kirk Hill Community Wind Farm.

Connects to the Kirk Hill dashboard API using your personal API key and provides live sensors for the whole farm and each individual turbine.

## Project notes

Owner/site generation kWh values are **live dynamic API values**. Owner/site financial earnings shown in the dashboard are **projected values** and **not real-time dynamic earnings**. All-time projected value now uses the API all-time timeframe start date when available.
Kirk Hill API remains the authoritative source for actual generation values. Open-Meteo integration is forecast-only and does not require a separate forecast API key.
Dev updates can be published as GitHub pre-releases for early testing while stable releases remain marked as Latest.
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
- **Published books finance inputs** — editable revenue/cost/distribution number entities for entering current figures from wind farm accounts
- **Open-Meteo forecast sensors** — optional next-hour / 3h / 24h wind-speed forecast context (non-authoritative), using automatic farm-location lookup
- **Per-turbine sensors** — power (owner + site), capacity factor (owner + site), wind speed, state text, and active binary sensor for each of the 8 turbines
- **Auto-generated Lovelace dashboard** — created automatically during setup with overview, finances, and turbines tabs containing:
  - A compact top-level Quick actions reload control that triggers integration reload
  - Taller turbine map viewport so all turbines fit more reliably on-screen
  - Active/inactive turbine count and alarm status
  - An **interactive turbine map** showing all 8 turbines with T1–T8 labels, running/stopped legend, hover titles, live spin animation proportional to output, scroll/pinch zoom, drag-to-pan, and double-click to reset
  - Full per-turbine detail cards

## Requirements

- A Kirk Hill Co-op membership with API access
- Your personal Kirk Hill dashboard API key

> **Not affiliated with Kirk Hill Co-op.** This is an independent community integration.
