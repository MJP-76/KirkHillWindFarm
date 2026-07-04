# Kirk Hill Wind Farm Integration

## ⚠️ **IMPORTANT V1 UPGRADE NOTICE**

**IF YOU INSTALLED THE INITIAL / V1 RELEASE, YOU MUST REMOVE THE HACS REPOSITORY AND THE INTEGRATION IN DEVICES & SERVICES, THEN RE-ADD THEM**

<a href="https://www.home-assistant.io/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white" alt="Home Assistant"></a>
<a href="https://github.com/hacs/integration" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
<a href="https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml/badge.svg" alt="HACS Validation"></a>
<a href="https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml" target="_blank" rel="noopener noreferrer"><img src="https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://github.com/features/copilot" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/GitHub%20Copilot-Built%20with-000000?style=flat-square&logo=githubcopilot" alt="GitHub Copilot"></a>

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

> **Not affiliated with Kirk Hill Co-op.** This is a community integration that
> reads the dashboard's public API endpoints with your personal API key.
>
> **Financial earnings figures are projected, not real-time dynamic values.**
>
> **Kirk Hill API remains the authoritative source for actual farm generation.**

It pulls current data for both OpenAPI scopes:
- `owner` (your ownership share)
- `site` (whole-site values)


<br>If you find this integration useful, or want to support further development you can support my work here:

<a href="https://www.buymeacoffee.com/mjp76" target="_blank" rel="noopener noreferrer"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

Or use my <a href="https://share.octopus.energy/iron-moose-196" target="_blank" rel="noopener noreferrer">Octopus Energy referral link</a> — you get GBP50 credit for joining, and I get GBP50 too.

## Features
- Live API polling (`cloud_polling` integration)
- Farm-level owner/site scoped sensors for:
  - power
  - capacity factor
  - generation by timeframe: yesterday, today, week, month, ytd, year, alltime
  - owner and site **projected** value by timeframe (GBP), based on configured annual projections (non-dynamic)
- Manual published-books finance inputs (editable number entities):
  - revenue
  - operating costs
  - finance costs
  - other costs
  - owner distribution
- Farm-level physical sensors (scope-independent):
  - wind speed
  - active turbines
  - inactive turbines
  - alarm binary sensor
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
- Open-Meteo forecast integration (forecast only; not used as authoritative actual generation)
- Configurable polling interval via Options
- Auto-generated Lovelace dashboard tab created during integration setup
- Dashboard follows the live entity IDs from your installed config entry
- Generation cards display values dynamically as kWh or MWh and round to 2 decimal places
- Dashboard YAML file included for manual import/customization
- Interactive turbine map with scroll/pinch zoom, drag-to-pan, and T1–T8 labels

## Installation
1. Add this repository to HACS (Custom Repositories)
2. Install "Kirk Hill Wind Farm"
3. Restart Home Assistant
4. Add the integration via Settings -> Devices & Services -> Add Integration -> "Kirk Hill Wind Farm"
5. Enter your API key, choose whether to create the dashboard automatically, and set a site name

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
- **Site name** — used as the integration title in Home Assistant

After setup, the **Configure** options let you change:

- **Polling interval**
- **Create dashboard automatically**
- **Owner projected annual earnings (GBP)**
- **Site projected annual earnings (GBP)**
- **Owner value rate (GBP per kWh)** (legacy compatibility)
- **Owner share (%)** (legacy compatibility)

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
- Open-Meteo forecast wind speed (next hour / next 3h avg / next 24h avg) [m/s] (forecast-only, non-authoritative)
- Published books revenue [GBP] (editable number)
- Published books operating costs [GBP] (editable number)
- Published books finance costs [GBP] (editable number)
- Published books other costs [GBP] (editable number)
- Published books owner distribution [GBP] (editable number)
- Wind speed [m/s]
- Active turbines
- Inactive turbines
- Alarm (binary sensor)

Timeframe generation entities keep a stable raw **kWh** state for reliability in Home Assistant. The generated dashboard formats those values for display as **kWh** or **MWh** automatically and rounds them to **2 decimal places**. Financial values are separate **projected** figures and are not calculated from live generation.

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
- Owner and site overview sections
- Dashboard range controls aligned with the Kirk Hill dashboard UX (`Today`, `Yesterday`, `7 days`, `30 days`, `year`, `All time`)
- Owner and site generation cards shown first in each overview section
- Owner generation cards show actual generation energy values (kWh/MWh) only
- Dedicated **Owner projected earnings** section listing projected monetary sensors for all timeframes
- Dedicated **Finances** tab with:
  - **Published books inputs** (editable revenue/cost/distribution figures)
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
- Generation display cards that switch between **kWh** and **MWh** automatically and show **2 decimal places**

The generated dashboard uses the **live entity registry** for the current config entry, so it follows your real entity IDs instead of relying on hardcoded names.
Dashboard structure and labels are periodically aligned against exported snapshots of `dashboard.kirkhillcoop.org` where possible, while maintaining Home Assistant entity/state model compatibility.

The animated map card is bundled by the integration and loaded automatically with the dashboard. From **v4.5.2**, the dashboard and frontend card are reloaded automatically whenever the integration starts or is reloaded — no manual page refresh or HA restart required.

For manual import or customization, a dashboard YAML is also provided at <a href="dashboards/kirkhill_wind_scada.yaml" target="_blank" rel="noopener noreferrer"><code>dashboards/kirkhill_wind_scada.yaml</code></a>.

## Version management

All release versions are tracked from a single source-of-truth file: <a href="VERSION" target="_blank" rel="noopener noreferrer"><code>VERSION</code></a>.

**Branch strategy:**
- `main` — stable releases
- Pre-releases and stable releases are both published from `main`

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
