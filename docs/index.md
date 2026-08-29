# Kirk Hill Wind Farm

[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

It pulls current data for both OpenAPI scopes:

- `owner` (your ownership share)
- `site` (whole-site values)

!!! warning "Financial figures are projected"

    Financial figures are *projected*, not real-time values, and are based on
    user-defined inputs. The Kirk Hill API remains the authoritative source for
    actual farm generation.

## Support me

If you find this project useful, and would like to help support its continued
development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## What this integration does

- **Live API polling** (`cloud_polling` integration)
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
- Per-turbine sensors:
  - power (`owner` + `site`)
  - capacity factor (`owner` + `site`)
  - wind speed, state text, active binary sensor, rotor speed, today's generation
- Config flow with API key validation and masked key entry
- Optional automatic dashboard creation during setup
- Configurable owner/site projected annual earnings (GBP)
- Open-Meteo forecast integration (forecast only; not authoritative actual generation)
- Optional experimental Ethex payment-tracking onboarding toggle
- Configurable polling interval via Options
- Auto-generated Lovelace dashboard tab with a SCADA single-line diagram, interactive turbine map, and bundled ApexCharts/Plotly chart cards
- Dashboard customisations are preserved across reloads and updates; `kirkhill_wind.reset_dashboard` restores defaults

## Where to go next

| Topic | Page |
|---|---|
| Install and configure | [Installation](installation.md) |
| Full entity reference | [Sensors](sensors.md) |
| Dashboard tabs and cards | [Dashboard](dashboard.md) |
| Turbine down/recovery WhatsApp alerts | [WhatsApp alerts](whatsapp-alerts.md) |
| Farm and turbine technical specs | [Farm reference](farm-reference.md) |
| Versioning and cutting releases | [Release management](development/release-management.md) |
| Full version history | [Changelog](changelog.md) |

[badge-hacs]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://github.com/hacs/integration
[badge-hacs-validation]: https://img.shields.io/badge/HACS%20Validation-passing-brightgreen
[workflow-hacs-validation]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/validate.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-ci]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml