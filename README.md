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
- Dashboard now follows the live entity IDs from your installed config entry
- Dashboard generation cards display values dynamically as kWh or MWh and round to 2 decimal places
- Dashboard YAML file is still included for manual import/customization

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
- owner and site overview sections
- owner and site generation cards shown first in each overview section
- all owner/site generation timeframe entities
- live farm wind and turbine availability
- a larger full-width animated turbine map on the **Turbines** tab
- automatic map zoom that fits all turbines by default
- turbine icons that spin in proportion to live output
- full per-turbine owner/site power, capacity, wind, state, and active status
- generation display cards that switch between **kWh** and **MWh** automatically and show **2 decimal places**

The generated dashboard now uses the **live entity registry** for the current config entry, so it follows your real entity IDs instead of relying on hardcoded names.

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
