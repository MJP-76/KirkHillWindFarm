# Kirk Hill Wind Farm Integration

[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]
[![Docs][badge-docs]][docs]

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

It pulls current data for both OpenAPI scopes:
- `owner` (your ownership share)
- `site` (whole-site values)

> - **Financial figures are projected, not real-time values and based on user-defined inputs.**
> - **Kirk Hill API remains the authoritative source for actual farm generation.**

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Features

- Live API polling (`cloud_polling` integration)
- Farm-level owner/site scoped sensors for: power, capacity factor, and generation by timeframe (yesterday, today, week, month, ytd, year, alltime), plus projected value by timeframe (GBP)
- Farm-level physical sensors (scope-independent): wind speed, active/inactive turbines, alarm binary sensor
- Per-turbine sensors for each of T1–T8: power, capacity factor, wind speed, state text, active state, today's generation
- Config flow with masked API key validation
- Optional automatic dashboard creation during setup
- Open-Meteo forecast integration (forecast only; not authoritative actual generation)
- Optional experimental Ethex payment-tracking onboarding toggle
- Configurable polling interval via Options
- Auto-generated dashboard: SCADA single-line diagram, interactive turbine map, and bundled ApexCharts/Plotly chart cards
- Dashboard customisations preserved across reloads/updates; `kirkhill_wind.reset_dashboard` restores defaults

## Installation

**Pre-Reqs**
*Generate your Kirk Hill Wind Farm API key by logging in to the dashboard https://dashboard.kirkhillcoop.org, clicking on your username / account in the top right corner, scrolling down to the API section, pressing "Generate" and copying the API key*

1. Add this repository to HACS (Custom Repositories)
2. Install "Kirk Hill Wind Farm"
3. Restart Home Assistant
4. Add the integration via Settings -> Devices & Services -> Add Integration -> "Kirk Hill Wind Farm"
5. Enter your API key, choose whether to create the dashboard automatically, and set a site name

>If you want to include your earnings from the Ethex Investment Platform, you will need to also add that repository https://github.com/mjp-76/ha-ethex
>Currently in testing awaiting the go live of Kirk Hill Wind Farm payments on Ethex

Polling interval can be changed later from the integration's **Configure** (Options) menu.
See the [docs](https://MJP-76.github.io/KirkHillWindFarm/installation/) for the full list of setup fields and options.

## Sensors

Timeframe generation entities keep a stable raw **kWh** state; the generated dashboard formats them with automatic unit scaling (kWh → MWh → GWh) rounded to 2 decimal places. Financial values are separate **projected** figures, not calculated from live generation.

Farm hub device: owner/site power and capacity factor, generation for all timeframes (owner + site), Open-Meteo forecast wind, wind speed, active/inactive turbines, and an alarm binary sensor (on when any turbine is in a thermal or electrical fault state).

Per-turbine devices (`Turbine T1` … `Turbine T8`): owner/site power and capacity factor, wind speed, state text, active binary sensor, today's and all-time site generation, rotor speed.

For the full entity reference see [Sensors](https://MJP-76.github.io/KirkHillWindFarm/sensors/).

## Notifications

Get a WhatsApp message when a turbine goes down (or comes back online) — an edge-triggered example setup using this integration's entities is in the [WhatsApp alerts guide](https://MJP-76.github.io/KirkHillWindFarm/whatsapp-alerts/).

## Dashboard

When you add the integration, it can auto-create a Lovelace dashboard tab (`kirk-hill-wind-dashboard`) with a SCADA tab, overview, Finances, History, and Turbines tabs, plus an interactive turbine map and bundled chart cards. User additions are preserved across updates; reset with `kirkhill_wind.reset_dashboard`. See [Dashboard](https://MJP-76.github.io/KirkHillWindFarm/dashboard/) for details.

For manual import or customization, a dashboard YAML is also provided at [`dashboards/kirkhill_wind_scada.yaml`][dashboard-yaml].

## Version management

All release versions are tracked from a single source-of-truth file: [`VERSION`][version-file]. The release flow (branch strategy and `version_sync.py` step) is documented in [Release management](https://MJP-76.github.io/KirkHillWindFarm/development/release-management/).

## Changelog

Full version history is kept in [`CHANGELOG.md`][changelog].

[badge-docs]: https://img.shields.io/badge/Docs-MkDocs-41BDF5?style=flat&logo=materialdesignicons&logoColor=white
[badge-home-assistant]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[home-assistant]: https://www.home-assistant.io/
[badge-hacs]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://github.com/hacs/integration
[badge-hacs-validation]: https://img.shields.io/badge/HACS%20Validation-passing-brightgreen
[workflow-hacs-validation]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/validate.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-ci]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml
[badge-release]: https://img.shields.io/github/v/release/MJP-76/KirkHillWindFarm?style=flat&label=Release
[releases]: https://github.com/MJP-76/KirkHillWindFarm/releases
[badge-built-with-ai]: https://img.shields.io/badge/Built%20with-AI-black?logo=openai&logoColor=white
[built-with-ai]: https://openai.com
[docs]: https://MJP-76.github.io/KirkHillWindFarm/
[dashboard-yaml]: dashboards/kirkhill_wind_scada.yaml
[version-file]: VERSION
[changelog]: CHANGELOG.md