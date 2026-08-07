# Kirk Hill Wind Farm Integration

[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]

<details>
<summary><strong>Kirk Hill Wind Farm — Technical Reference</strong> — click to expand</summary>

Onshore wind farm near Kirkoswald, South Ayrshire, Scotland. Coordinates: 55.3064, -4.7399.

**Turbines**
- 8 × Enercon E92/2350 wind energy converters
- Rated 2.35 MW each, 18.8 MW total nameplate capacity
- Gearbox-free (direct drive) design, manufactured in Germany
- Peak output reached at wind speeds of 14 m/s or more (27.2 knots)

**Electrical / Grid Connection**
- 33 kV collection network
- 33 kV switchgear
- Client substation building on site
- Underground cabling between turbines and substation, and to the point of connection
- Grid connection to the Scottish Power (SP Energy Networks) network via a new substation
- Connection route: ~6 km total, comprising overhead line (~5 km, 70 poles) and ~1 km underground cable

**Civil / Balance of Plant**
- Eight turbine foundations and crane hard standings
- ~4,000 m of new access tracks
- New permanent site entrance

**Performance**
- Expected annual generation: ~54,000 MWh
- Cumulative generation to end of June 2026: 118,175,429 kWh (per kirkhillcoop.org)

**Sources**
- [Kirk Hill Co-op](https://kirkhillcoop.org) — official co-op site, turbines, performance and ownership info
- [kirkhillcoop.org/our-story](https://kirkhillcoop.org/our-story) — project history and build timeline
- [kirkhillcoop.org/the-windfarm](https://kirkhillcoop.org/the-windfarm) — turbine and site specifications
- [Knights Brown — Kirk Hill Wind Farm](https://knightsbrown.co.uk/project/kirk-hill-wind-farm/) — balance of plant works (substation, cabling, civils)
- [Kirk Hill Dashboard API docs](https://dashboard.kirkhillcoop.org/api-docs) — OpenAPI reference for the farm data endpoints

</details>

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

It pulls current data for both OpenAPI scopes:
- `owner` (your ownership share)
- `site` (whole-site values)
> - **Financial figures are projected, not real-time values and based on user-defined inputs.**
> - **Kirk Hill API remains the authoritative source for actual farm generation.**

## Version 4.8.16 (stable)
- **State restoration for generation sensors**: farm and turbine generation sensors now restore their last known values on Home Assistant restart, avoiding "—" gaps while waiting for slow-tier API fetches
- Added `RestoreEntity` to `FarmGenerationByTimeframeSensor`, `TurbineGenerationTodaySensor`, `TurbineGenerationAlltimeSensor`

## Version 4.8.15 (stable)
- **Overview tab removed**: dashboard now starts with SCADA, then Finances, History, Turbines
- **Finances tab moved to second position** (after SCADA)
- **Obsolete view cleanup**: Overview view automatically removed from existing dashboards on merge

## Version 4.8.14 (stable)
- **Overview cleanup**: removed KPI row (Alarm tile, Reload button) and Site metrics card; Overview now shows only Owner/Site generation markdown cards
- **Finances tab fixed**: now shows generation kWh alongside projected earnings for all timeframes (Owner & Site), not just monetary values
- **Obsolete card/section cleanup**: removed cards/sections automatically pruned on dashboard merge

## Version 4.8.13 (stable)
- **SCADA dashboard redesign**: alarm + active turbines moved above turbine list (left), always-visible alarm chip (OK / flashing ALARM), cleaner National Grid box, renamed wind chips (Current Wind / Forecast 1h), new Site Capacity chip
- **Capacity Factor moved**: removed from Overview KPI row and Site metrics; added to SCADA dashboard as "Site Capacity"
- **Bus summary removed** (redundant with National Grid box)
- **Turbine status legend moved** to left side below turbine list
- **Dashboard customisation preserved** with factory reset options documented

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Features
- Live API polling (`cloud_polling` integration)
- Farm-level owner/site scoped sensors for:
  - power
  - capacity factor
  - generation by timeframe: yesterday, today, week, month, ytd, year, alltime
  - owner and site **projected** value by timeframe (GBP), based on configured annual projections (non-dynamic)
- Farm-level physical sensors (scope-independent):
  - wind speed
  - active turbines
  - inactive turbines
  - alarm binary sensor
- Validation hardening for turbine count sensor handling (active/inactive)
- Per-turbine sensors:
  - power (`owner` + `site`)
  - capacity factor (`owner` + `site`)
  - wind speed
  - state text
  - active binary sensor
- Config flow with API key validation
- Masked API key entry in the setup form
- Optional automatic dashboard creation during setup
- Configurable owner projected annual earnings (GBP)
- Configurable site projected annual earnings (GBP)
- Legacy compatibility options: owner share (%) and owner value rate (GBP per kWh)
- Published-books/AGM manual finance inputs removed; projected owner/site figures remain
- Open-Meteo forecast integration (forecast only; not used as authoritative actual generation)
- No forecast API key required (Open-Meteo is used automatically)
- Optional experimental Ethex payment-tracking onboarding toggle in config flow
- Configurable polling interval via Options
- Auto-generated Lovelace dashboard tab created during integration setup
- Compact icon-only reload control at the top of the dashboard that calls integration reload
- Dashboard follows the live entity IDs from your installed config entry
- Generation cards display values dynamically with scaled units (kWh, MWh, GWh, TWh, PWh, EWh) and round to 2 decimal places
- Dashboard YAML file included for manual import/customization
- Interactive turbine map with scroll/pinch zoom, drag-to-pan, and T1–T8 labels
- Taller turbine map viewport for improved full-farm fit on the Turbines tab
- **Bundled chart cards** — ApexCharts and Plotly cards are shipped with the integration (no separate HACS installs needed)
- **Dual-axis Power chart** — site power (MW) and owner power (kW) on separate Y-axes (6-hour history)
- **Power vs Wind scatter plot** — correlation between wind speed and site power output (24-hour history)
- **Combined Power and Wind history graph** — owner power, site power, and wind speed on a single chart
- **SCADA tab** — the first tab on the dashboard, a full-bleed animated single-line diagram of the farm (turbines → bus → transformer → grid) with live per-turbine power, status, today's generation and rotor speed
- **Dashboard customisation preserved** — user-added cards, sections, and views are retained across integration reloads and updates
- **Reset dashboard service** — `kirkhill_wind.reset_dashboard` restores the dashboard to integration defaults

## Installation
**Pre-Reqs**
*Generate your Kirk Hill Wind Farm API key by logging in to the dashboard https://dashboard.kirkhillcoop.org, clicking on your username / account in the top right corner, scrolling down to the API section, pressing "Generate" and copying the API key*

1. Add this repository to HACS (Custom Repositories)
2. Install "Kirk Hill Wind Farm"
3. Restart Home Assistant
4. Add the integration via Settings -> Devices & Services -> Add Integration -> "Kirk Hill Wind Farm"
5. Enter your API key, choose whether to create the dashboard automatically, and set a site name

>If you want to include your earnings from the Ethex Investment Platform, you will need to also add that repository https://github.com/mjp-76/ha-ethex
>Currently in testing awaitng the go live of Kirk Hill Wind Farm payments omn Ethex

Polling interval can be changed later from the integration's **Configure** (Options) menu.

## Configuration

During setup, the integration asks for:

- **API key** — entered as a masked password field in Home Assistant
- **Create dashboard automatically** — choose whether the integration should create/update its Lovelace dashboard tab
- **Owner projected annual earnings (GBP)** — annual projected owner earnings used to derive timeframe values (non-dynamic)
- **Site projected annual earnings (GBP)** — annual projected site value used to derive timeframe values (non-dynamic)
- **Owner value rate (GBP per kWh)** — legacy setting retained for compatibility
- **Owner share (%)** — legacy setting retained for compatibility
- **Forecast source** — Open-Meteo is used automatically for forecast sensors using farm-location lookup (no forecast API key required)
- **Enable payment tracking onboarding (Ethex, experimental)** — optionally starts Ethex setup flow to configure payment tracking
- **Site name** — used as the integration title in Home Assistant

After setup, the **Configure** options let you change:

- **Polling interval**
- **Create dashboard automatically**
- **Owner projected annual earnings (GBP)**
- **Site projected annual earnings (GBP)**
- **Owner value rate (GBP per kWh)** (legacy compatibility)
- **Owner share (%)** (legacy compatibility)
- **Enable payment tracking onboarding (Ethex, experimental)**

## Sensors

Farm hub device:
- Power (owner) [kW]
- Power (site) [MW]
- Capacity factor (owner) [%]
- Capacity factor (site) [%]
- Generation (yesterday) [kWh] for owner and site
- Generation (today) [kWh] for owner and site
- Generation (week) [kWh] for owner and site
- Generation (month) [kWh] for owner and site
- Generation (ytd) [kWh] for owner and site
- Generation (year) [kWh] for owner and site
- Generation (alltime) [kWh] for owner and site
- Generation source attribute marks these entities as `api_dynamic`
- Projected value (yesterday/today/week/month/ytd/year/alltime) [GBP] for owner and site is non-dynamic
  - For **all-time projected value**, the projection window start date is derived from the API all-time timeframe when available
- Open-Meteo forecast wind speed (next hour / next 3h avg / next 24h avg) [m/s] (forecast-only, non-authoritative)
- Wind speed [m/s]
- Active turbines
- Inactive turbines
- Alarm (binary sensor) — on when any turbine is in an actual thermal or electrical fault state

Timeframe generation entities keep a stable raw **kWh** state for reliability in Home Assistant. The generated dashboard formats those values for display with automatic unit scaling (**kWh**, **MWh**, **GWh**, **TWh**, **PWh**, **EWh**) and rounds them to **2 decimal places**. Financial values are separate **projected** figures and are not calculated from live generation.

Per turbine device (`Turbine T1` ... `Turbine T8`):
- Power (owner) [kW]
- Power (site) [kW]
- Capacity factor (owner) [%]
- Capacity factor (site) [%]
- Wind speed (m/s)
- State text
- Active (binary sensor)
- Generation today (site) [kWh]
- Generation all-time (site) [kWh]
- Rotor speed [rpm]
- Today's generation share attribute (`share_percent`)

## Dashboard

When you add the integration, it can auto-create a Lovelace dashboard tab (`kirk-hill-wind-dashboard`) in the sidebar.

The generated dashboard includes:
- A compact top-level **icon-only reload control** that calls `kirkhill_wind.reload_integration`
- A **SCADA tab** (the first tab) showing a full-bleed animated single-line diagram of the farm: 8 turbines feeding the site collection bus, through the step-up transformer, into the national grid. Each turbine shows live power, colour-coded status, last status time, today's generation and rotor speed; flow dots animate in proportion to power. The national grid block shows **Owner and Site** export power and to-grid-today side by side, the header shows live wind, active-turbine and next-hour forecast chips, and a **flashing ALARM indicator** appears while the farm alarm is on. Rendered as a panel view so it fills the entire tab.
- Owner and site overview sections
- Dashboard range controls aligned with the Kirk Hill dashboard UX (`Today`, `Yesterday`, `7 days`, `30 days`, `year`, `All time`)
- Owner and site generation cards shown first in each overview section
- Owner generation cards show actual generation energy values with automatic unit scaling (kWh, MWh, GWh, TWh, PWh, EWh)
- Dedicated **Finances** tab with:
  - **Owner finances** projected timeframe value sensors
  - **Site finances** projected timeframe value sensors
- A **History** tab with the chart cards:
  - **Combined Power and Wind** history graph — owner power, site power, and wind speed on a single chart
  - **Dual-axis Power chart** (ApexCharts) — site power (MW) and owner power (kW) on separate Y-axes
  - **Power vs Wind scatter plot** (Plotly) — wind speed (m/s) vs site power (MW) correlation
- Open-Meteo forecast wind speed (next hour) shown as a **Forecast** chip on the SCADA tab
- All owner/site generation timeframe entities
- Live farm wind and turbine availability
- A dedicated **Turbines** tab containing:
  - **Turbine status overview** card — active turbines, inactive turbines, and alarm state
  - **Interactive turbine map** — a full-width animated map card with:
    - T1–T8 labels above each turbine marker
    - Turbine icons that spin in proportion to live site capacity factor
    - Active/inactive state shown by marker colour
    - Running/stopped legend and per-turbine hover title (state + current detail + status time when available)
    - Fixed zoom level (zoom 15) centred on the farm
    - **Scroll wheel** to zoom in/out centred on the cursor
    - **Drag** to pan around the map
    - **Pinch** to zoom on touch devices
    - **Double-click / double-tap** to reset to the default view
  - Per-turbine owner/site power, capacity, wind, state, and active status cards
- Generation display cards that switch automatically between **kWh**, **MWh**, **GWh**, **TWh**, **PWh**, and **EWh**, showing **2 decimal places**

### Dashboard customisation

User-added cards, sections, and views are **preserved** across integration reloads and updates. The integration only updates the cards it manages — anything you add yourself is kept, and removed default cards are pruned without touching your additions.

### Factory reset the dashboard

Your customisations stay until you **explicitly** wipe them. There are two ways to start over:

**Option 1 — untick and rebuild from the integration**

1. Go to **Settings → Devices & Services → Kirk Hill Wind Farm → Configure**.
2. **Untick "Create dashboard automatically"** and save — the integration stops managing the dashboard, so nothing can be overwritten.
3. In the dashboard editor, **delete the `Kirk Hill Wind Farm` tab**.
4. **Re-tick "Create dashboard automatically"** (or reload the integration) — a fresh default dashboard is generated.

**Option 2 — reset immediately**

Call the `kirkhill_wind.reset_dashboard` service:

```yaml
service: kirkhill_wind.reset_dashboard
```

This restores the dashboard to the integration defaults and **discards all customisations**.

### Bundled chart cards

The ApexCharts and Plotly Lovelace cards are bundled with the integration and registered automatically. No separate HACS installation is required for the dashboard charts.

### Frontend cards

The animated map card and chart cards are bundled by the integration and loaded automatically with the dashboard. From **v4.5.2**, the dashboard and frontend cards are reloaded automatically whenever the integration starts or is reloaded — no manual page refresh or HA restart required.

For manual import or customization, a dashboard YAML is also provided at [`dashboards/kirkhill_wind_scada.yaml`][dashboard-yaml].

## Version management

All release versions are tracked from a single source-of-truth file: [`VERSION`][version-file].

**Branch strategy:**
- `main` — stable releases
- Pre-releases and stable releases are both published from `main`
- Release cadence can include both in sequence: a stable **Latest** tag, then a dev **Pre-release** tag
- Stable updates are always published as GitHub **Latest** releases
- Stable release flow includes a full merge into `main` before tagging/publishing

When preparing a release:
1. Update `VERSION` (use `X.Y.Z`, for example `4.5.2`).
2. Run `python scripts/version_sync.py sync` to update:
   - `custom_components/kirkhill_wind/manifest.json`
   - `pyproject.toml`
3. Validate with `python scripts/version_sync.py check`.
4. Commit and push to `main`.
5. Tag and create a GitHub release:
   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   gh release create vX.Y.Z --title vX.Y.Z --generate-notes [--prerelease] --target <branch>
   ```

Release tags are generated as `vX.Y.Z` directly from `VERSION`.

[badge-home-assistant]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[home-assistant]: https://www.home-assistant.io/
[badge-hacs]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://github.com/hacs/integration
[badge-hacs-validation]: https://img.shields.io/badge/HACS%20Validation-passing-brightgreen
[workflow-hacs-validation]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/validate.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml
[badge-release]: https://img.shields.io/github/v/release/MJP-76/KirkHillWindFarm?style=flat&label=Release
[releases]: https://github.com/MJP-76/KirkHillWindFarm/releases
[badge-built-with-ai]: https://img.shields.io/badge/Built%20with-AI-black?logo=openai&logoColor=white
[built-with-ai]: https://openai.com
