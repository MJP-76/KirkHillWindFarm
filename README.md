# Kirk Hill Wind Farm Integration

[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]

<details>
<summary><strong>Wind farm Info</strong> — click to expand</summary>

```
Kirk Hill Wind Farm Info

Reference notes about the wind farm. Add or update these whenever we learn
something new about the farm.

Overview

Kirk Hill Wind Farm is an onshore wind facility located in Kirkoswald, South
Ayrshire, Scotland. It is the UK's largest consumer-owned wind farm, run on a
community cooperative model.

Technical Specifications

The site utilizes eight Enercon E82 wind energy converters. The total nameplate
output is 18.8 Megawatts (MW), with each turbine rated at 2.35 MW. The turbines
reach peak power output in wind speeds of 14 metres per second (approx. 31 mph)
or higher. The farm is expected to generate roughly 54,000 to 56,000 Megawatt
Hours (MWh) per year, which is enough clean energy to power approximately 20,000
households and businesses.

Location & Construction Timeline

The site is situated near the coastal village of Kirkoswald in South Ayrshire,
offering distinctive views toward the Ailsa Craig volcanic island. Turbine 2 is
officially named "Ailsa" by co-op members. Pre-construction works began in early
2022. The first power was successfully generated and synchronized to the grid in
April 2024, with full commercial operations launching in July 2024.

Ownership & Co-operative Structure

Kirk Hill Wind Farm is owned and operated by Kirk Hill Wind Farm Ltd, a joint
venture between Kirk Hill Coop Ltd (the majority shareholder, with 5,600+ members
across the UK) and Bruntwood Ltd, a property company based in Manchester. Each
member purchased a "wattage amount" of generation capacity for the 25-year
lifetime of the project. Members benefit from zero carbon electricity delivered
via the national grid and receive a share of the profit from the sale of their
electricity to suppliers, less grid charges and the costs of running the farm —
helping to stabilise their energy bills over time.

The project was originally developed and managed by Ripple Energy Limited before
it entered administration in March 2025. This did not affect the wind farm:
ownership had already been transferred to Kirk Hill Wind Farm Ltd, with separate
service contracts in place to manage the site day to day. Neither Ripple Energy
Limited nor its administrators have any legal relationship with the wind farm,
Kirk Hill Wind Farm Ltd or Kirk Hill Coop Ltd.

The wind farm is now professionally managed by Communities for Renewables CIC
(CfR) and will soon begin an onboarding process with member registrar Ethex.
Kirk Hill Coop Limited is a co-operative society registered with the Financial
Conduct Authority (registration number 4829), and is the majority shareholder in
the UK's largest community wind farm project. Registered address: Communities
for Renewables CIC, Redruth House, Business Park West, Scorrier, Cornwall,
TR16 5EZ. Website: https://kirkhillcoop.org
```

</details>

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

It pulls current data for both OpenAPI scopes:
- `owner` (your ownership share)
- `site` (whole-site values)
> **Not affiliated with Kirk Hill Co-op.** This is a community integration that
> reads the dashboard's public API endpoints with your personal API key.
>
> **Financial earnings figures are projected, not real-time dynamic values.**
>
> **Kirk Hill API remains the authoritative source for actual farm generation.**

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
*Generate you Kirk Hill Wind Farm API by logging in to the dashboard https://dashboard.kirkhillcoop.org, clicking on your username / account in teh top right cornner, scroll down to the API section, press "Generate" and copy the API key*

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
- Alarm (binary sensor)

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
- A **SCADA tab** (the first tab) showing a full-bleed animated single-line diagram of the farm: 8 turbines feeding the site collection bus, through the step-up transformer, into the national grid. Each turbine shows live power, colour-coded status, last status time, today's generation and rotor speed; flow dots animate in proportion to power. Rendered as a panel view so it fills the entire tab.
- Owner and site overview sections
- Dashboard range controls aligned with the Kirk Hill dashboard UX (`Today`, `Yesterday`, `7 days`, `30 days`, `year`, `All time`)
- Owner and site generation cards shown first in each overview section
- Owner generation cards show actual generation energy values with automatic unit scaling (kWh, MWh, GWh, TWh, PWh, EWh)
- Dedicated **Owner projected earnings** section listing projected monetary sensors for all timeframes
- Dedicated **Finances** tab with:
  - **Owner finances** projected timeframe value sensors
  - **Site finances** projected timeframe value sensors
- Open-Meteo forecast entities included directly in **Site metrics** alongside actual wind speed from Kirk Hill API
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
- A **Charts** section with:
  - **Combined Power and Wind** history graph — owner power, site power, and wind speed on a single chart
  - **Dual-axis Power chart** (ApexCharts) — site power (MW) and owner power (kW) on separate Y-axes
  - **Power vs Wind scatter plot** (Plotly) — wind speed (m/s) vs site power (MW) correlation

### Dashboard customisation

User-added cards, sections, and views are **preserved** across integration reloads and updates. The integration only updates the cards it manages — anything you add yourself is kept.

If you want to reset the dashboard to its default layout, use the `kirkhill_wind.reset_dashboard` service:

```yaml
service: kirkhill_wind.reset_dashboard
```

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
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/hassfest.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/hassfest.yml
[badge-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml
[badge-release]: https://img.shields.io/github/v/release/MJP-76/KirkHillWindFarm?style=flat&label=Release
[releases]: https://github.com/MJP-76/KirkHillWindFarm/releases
[badge-built-with-ai]: https://img.shields.io/badge/Built%20with-AI-black?logo=openai&logoColor=white
[built-with-ai]: https://openai.com
