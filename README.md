# Kirk Hill Wind Farm Integration

[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hacs-validation]
[![CI][badge-ci]][workflow-ci]
[![GitHub Copilot][badge-copilot]][github-copilot]

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

It pulls current data for both OpenAPI scopes:
- `owner` (your ownership share)
- `site` (whole-site values)

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

> **Not affiliated with Kirk Hill Co-op.** This is a community integration that
> reads the dashboard's public API endpoints with your personal API key.
>
> **Financial earnings figures are projected, not real-time dynamic values.**
>
> **Kirk Hill API remains the authoritative source for actual farm generation.**

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

## Installation
**Pre-Reqs**
*Generate you Kirk Hill Wind Farm API by logging in to the dashboard https://dashboard.kirkhillcoop.org, clicking on your username / account in teh top right cornner, scroll down to the API section, press "Generate" and copy the API key*

1. Add this repository to HACS (Custom Repositories)
2. Install "Kirk Hill Wind Farm"
3. Restart Home Assistant
4. Add the integration via Settings -> Devices & Services -> Add Integration -> "Kirk Hill Wind Farm"
5. Enter your API key, choose whether to create the dashboard automatically, and set a site name

>If you want to include your earnings from the Ethex Investment Platform, you will need to also add that reposity https://github/mjp-76/ha-ethex
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

## Dashboard

When you add the integration, it can auto-create a Lovelace dashboard tab (`kirk-hill-wind-dashboard`) in the sidebar.

The generated dashboard includes:
- A compact top-level **icon-only reload control** that calls `kirkhill_wind.reload_integration`
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

The generated dashboard uses the **live entity registry** for the current config entry, so it follows your real entity IDs instead of relying on hardcoded names.
Dashboard structure and labels are periodically aligned against exported snapshots of `dashboard.kirkhillcoop.org` where possible, while maintaining Home Assistant entity/state model compatibility.

The animated map card is bundled by the integration and loaded automatically with the dashboard. From **v4.5.2**, the dashboard and frontend card are reloaded automatically whenever the integration starts or is reloaded — no manual page refresh or HA restart required.

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

## License

MIT

[badge-home-assistant]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[badge-hacs]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[badge-hacs-validation]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml/badge.svg
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/validate.yml?branch=main&label=Hassfest
[badge-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml/badge.svg
[badge-copilot]: https://img.shields.io/badge/GitHub%20Copilot-Built%20with-000000?style=flat-square&logo=githubcopilot
[badge-buy-me-a-coffee]: https://cdn.buymeacoffee.com/buttons/default-orange.png
[home-assistant]: https://www.home-assistant.io/
[hacs]: https://github.com/hacs/integration
[workflow-hacs-validation]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[workflow-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml
[github-copilot]: https://github.com/features/copilot
[buy-me-a-coffee]: https://www.buymeacoffee.com/mjp76
[octopus-referral]: https://share.octopus.energy/iron-moose-196
[dashboard-yaml]: dashboards/kirkhill_wind_scada.yaml
[version-file]: VERSION
