# Kirk Hill Wind Farm Integration

[![Documentation][badge-docs]][docs]
[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]

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

## Quick start

1. Add this repository to **HACS → Settings → Custom Repositories** as an integration.
2. Install **Kirk Hill Wind Farm**.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add Integration → "Kirk Hill Wind Farm"**.
5. Enter your API key, choose whether to create the dashboard automatically, and set a site name.

> Pre-req: generate your Kirk Hill Wind Farm API key by logging in to the
> dashboard <https://dashboard.kirkhillcoop.org>, click your username in the top
> right, scroll to the API section, select **Generate**, and copy the key.

> Want to include earnings from the Ethex Investment Platform? Add
> <https://github.com/mjp-76/ha-ethex> too (experimental; awaiting Ethex go-live).

## Feature highlights

- Live `cloud_polling` integration for owner/site power, capacity factor, and generation by timeframe
- Per-turbine sensors for T1–T8 (power, capacity factor, wind speed, state, active, generation)
- Projected owner/site value by timeframe (GBP), config flow, and optional auto-dashboard
- Auto-generated Lovelace dashboard: SCADA single-line diagram, interactive turbine map, and bundled ApexCharts/Plotly chart cards

## Documentation

Full documentation is available at **[https://MJP-76.github.io/KirkHillWindFarm/][docs]**

| Topic | Link |
|---|---|
| Install and configure | [Installation](https://MJP-76.github.io/KirkHillWindFarm/installation/) |
| All sensor entities | [Sensors](https://MJP-76.github.io/KirkHillWindFarm/sensors/) |
| Dashboard tabs and cards | [Dashboard](https://MJP-76.github.io/KirkHillWindFarm/dashboard/) |
| Turbine down/recovery notifications | [WhatsApp alerts](https://MJP-76.github.io/KirkHillWindFarm/whatsapp-alerts/) |
| Version history | [Changelog](https://MJP-76.github.io/KirkHillWindFarm/changelog/) |

For manual dashboard import or customization, see [`dashboards/kirkhill_wind_scada.yaml`][dashboard-yaml].

## Changelog

Full version history is kept in [`CHANGELOG.md`][changelog].

[badge-docs]: https://img.shields.io/badge/Documentation-41BDF5?style=flat-square&logo=bookstack&logoColor=white
[docs]: https://MJP-76.github.io/KirkHillWindFarm/
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
[dashboard-yaml]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/dashboards/kirkhill_wind_scada.yaml
[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
