# Kirk Hill Wind Farm Integration

## ⚠️ **IMPORTANT V1 UPGRADE NOTICE**

**IF YOU INSTALLED THE INITIAL / V1 RELEASE, YOU MUST REMOVE THE HACS REPOSITORY AND THE INTEGRATION IN DEVICES & SERVICES, THEN RE-ADD THEM**

[![Home Assistant][ha-badge]][home-assistant]
[![hacs][hacs-badge]][hacs]
[![GitHub][github-badge]][repo]
[![GitHub Copilot][copilot-badge]][copilot]

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

> **Not affiliated with Kirk Hill Co-op.** This is a community integration that
> reads the dashboard's public API endpoints with your personal API key.

It pulls current data for both OpenAPI scopes:
- `owner` (your ownership share)
- `site` (whole-site values)


<br>If you find this integration useful, or want to support further development you can support my work here:

<a href="https://www.buymeacoffee.com/mjp76" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

Or use my [Octopus Energy referral link](https://share.octopus.energy/iron-moose-196) — you get GBP50 credit for joining, and I get GBP50 too.

## Features
- Live API polling (`cloud_polling` integration)
- Farm-level owner/site scoped sensors for:
  - power
  - capacity factor
  - generation by timeframe: yesterday, today, week, month, ytd, year, alltime
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
- **Site name** — used as the integration title in Home Assistant

After setup, the **Configure** options let you change:

- **Polling interval**
- **Create dashboard automatically**

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
- Wind speed [m/s]
- Active turbines
- Inactive turbines
- Alarm (binary sensor)

Timeframe generation entities keep a stable raw **kWh** state for reliability in Home Assistant. The generated dashboard formats those values for display as **kWh** or **MWh** automatically and rounds them to **2 decimal places**.

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
- Owner and site generation cards shown first in each overview section
- All owner/site generation timeframe entities
- Live farm wind and turbine availability
- A dedicated **Turbines** tab containing:
  - **Turbine status overview** card — active turbines, inactive turbines, and alarm state
  - **Interactive turbine map** — a full-width animated map card with:
    - T1–T8 labels above each turbine marker
    - Turbine icons that spin in proportion to live site capacity factor
    - Active/inactive state shown by marker colour
    - Fixed zoom level (zoom 15) centred on the farm
    - **Scroll wheel** to zoom in/out centred on the cursor
    - **Drag** to pan around the map
    - **Pinch** to zoom on touch devices
    - **Double-click / double-tap** to reset to the default view
  - Per-turbine owner/site power, capacity, wind, state, and active status cards
- Generation display cards that switch between **kWh** and **MWh** automatically and show **2 decimal places**

The generated dashboard uses the **live entity registry** for the current config entry, so it follows your real entity IDs instead of relying on hardcoded names.

The animated map card is bundled by the integration and loaded automatically with the dashboard. After upgrading, reload the integration or restart Home Assistant so the new frontend resource is picked up.

For manual import or customization, a dashboard YAML is also provided at [`dashboards/kirkhill_wind_scada.yaml`](dashboards/kirkhill_wind_scada.yaml).

## Version management

All release versions are tracked from a single source-of-truth file: [`VERSION`](VERSION).

When preparing a release:
1. Update `VERSION` (use `X.Y.Z`, for example `4.3.1`).
2. Run `python scripts/version_sync.py sync` to update:
   - `custom_components/kirkhill_wind/manifest.json`
   - `pyproject.toml`
3. Validate with `python scripts/version_sync.py check`.
4. Commit and push.
5. Create tag + GitHub release from the same version with `python scripts/version_sync.py release`.

Release tags are generated as `vX.Y.Z` directly from `VERSION`.

## License

MIT

[kirkhill]: https://dashboard.kirkhillcoop.org
[brands]: https://github.com/home-assistant/brands
[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[home-assistant]: https://www.home-assistant.io/
[ha-badge]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[repo]: https://github.com/MJP-76/KirkHillWindFarm
[github-badge]: https://img.shields.io/badge/GitHub-Repository-181717?style=flat-square&logo=github
[copilot]: https://github.com/features/copilot
[copilot-badge]: https://img.shields.io/badge/GitHub%20Copilot-Built%20with-000000?style=flat-square&logo=githubcopilot
