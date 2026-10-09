# Kirk Hill Wind Farm

[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]

A Home Assistant custom component for the Kirk Hill Wind Farm dashboard API.

It pulls current data for both OpenAPI scopes:

- `owner` (your ownership share)
- `site` (whole-site values)

!!! warning "Financial figures — shown but deliberately empty"

    **As of v4.16.2 the money UI is on the card but nothing is populated.** The
    £ value column, both £/h cells, both price pills and the member-savings line
    are drawn **empty** — every money cell reads `—` and the Owner pill reads
    `Rate —` — because all **22 earnings entities are disabled** in the entity
    registry and all three inputs (`owner_price_p_kwh`, `owner_rate_p_w`,
    `negotiated_price_gbp_mwh`) are `0.0`.

    This is deliberate and temporary: the integration had two competing bases —
    `kWh × p/kWh` for timeframes and `watts × p/W` for capacity — and rather
    than guess which the board means, nothing is calculated until they confirm
    how member payments are calculated. The empty cells are kept as a visual
    reminder. Generation, power and capacity are unaffected; re-enable an entity
    with `hab entity enable <entity_id>` to bring a figure back.

    Separately, the **All-time** and **past-year (2025, 2024)** £ values are
    suppressed (showing `—`), because the API records energy only — never money.
    See
    [Development decisions](development/decisions.md#owner-share-and-earnings-figures).

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
  - owner and site value by timeframe (GBP) — **empty from v4.16.1**: the entities exist but are disabled, so the column is drawn with `—` in every cell (previously `live generation × configured price`)
- Farm-level physical sensors (scope-independent):
  - wind speed
  - active turbines
  - inactive turbines
  - alarm binary sensor
- Per-turbine sensors:
  - power (`owner` + `site`)
  - capacity factor (`owner` + `site`)
  - wind speed, state text, active binary sensor, rotor speed, today's generation
- Config flow with masked API key entry, validated against the API
- Optional automatic dashboard creation during setup
- Configurable prices: Owner price (p/kWh), Owner rate (p/W) and Site/CfD price (£/MWh) as `number` entities — **all three disabled from v4.16.1** pending the board's model
- Open-Meteo forecast integration (forecast only; not authoritative actual generation)
- Optional experimental Ethex payment-tracking onboarding toggle
- Configurable polling interval via Options
- Auto-generated Lovelace dashboard: SCADA (single-line diagram, API status pill, Owner/Site Capacity panels with per-timeframe generation plus an **empty £ value column** — earnings entities disabled from v4.16.1, so no figure is calculated — Wind Speed detail modal, pop-out charts including a labelled turbine activity swimlane). History removed in v4.8.77, Finances retired into the SCADA card in v4.8.79, and the Turbines tab removed in v4.8.80 (its standalone map card deprecated in v4.8.81).
- Dashboard customisations are preserved across reloads and updates; `kirkhill_wind.reset_dashboard` restores defaults

## Where to go next

| Topic | Page |
|---|---|
| Install and configure | [Installation](installation.md) |
| Full entity reference | [Sensors](sensors.md) |
| Dashboard tabs and cards | [Dashboard](dashboard.md) |
| Turbine down/recovery WhatsApp alerts | [WhatsApp alerts](whatsapp-alerts.md) |
| Farm and turbine technical specs | [Farm reference](farm-reference.md) |
| What the upstream API contains, and what it has changed | [The Kirk Hill API](api.md) |
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