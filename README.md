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

> - **Money is a panel, not a column.** The Owner and Site panels carry
>   generation, power, capacity and wind only — the `Value (£)` column, the
>   `£/h` cells, the Member savings line and both price pills are gone. A
>   **Return on investment** panel leads the right column above them, in the
>   same box, showing the headline: invested amount, payments from Co-op,
>   your estimates, all payments and your return — click it for the full ledger
>   (every period the board declared a p/W rate for, its £ figure and ROI) and
>   the add/edit forms. The old price/rate entities stay disabled and zeroed
>   while the model is confirmed. Generation, power and capacity are unaffected.
> - **Kirk Hill API remains the authoritative source for actual farm generation.**

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Features

The integration polls the Kirk Hill Wind Farm API and turns it into live sensors
and an animated dashboard.

- **Owner & Site scopes** — pulls data for both your ownership share (`owner`)
  and the whole farm (`site`), covering power, capacity factor, and generation
  for yesterday, today, week, month, YTD, year, and all time. **The Owner and
  Site panels carry no money**: the GBP value sensors still exist but are
  disabled, and both show generation, capacity and wind only.
- **Prices are dormant** — `number.<farm>_owner_price_p_kwh`,
  `number.<farm>_owner_rate_p_w` and `number.<farm>_negotiated_price_gbp_mwh`
  remain in the codebase but are disabled and set to `0.0`; nothing reads them.
  Rates now live per declared period in the ledger.
- **Return on investment panel** — the top panel of the right column, above
  Owner and Site, in the same box and columns: invested amount, payments from
  Co-op, your estimates, all payments, return, period count, published rate
  and the current period. Click it for the ledger modal — one row per period (months,
  rate × watts, £, ROI %, the capital/interest split as reported by Ethex or
  the board, board or yours), the invested input and the add/edit
  forms. ROI is `value ÷ invested × 100`, deliberately not annualised, and
  reads `—` until you say what you invested.
- **Payment ledger** — `sensor.<farm>_payment_ledger` sums what the board has
  actually declared (`watts × p/W ÷ 100` per period), reads `unknown` until
  something is declared, and **withholds any figure for an undeclared period**
  until the board publishes the capital/interest split — no estimate is
  derived. Entries change only through the
  `kirkhill_wind.add_payment_record` / `update_payment_record` /
  `remove_payment_record` / `set_invested_amount` services.
- **Live SCADA dashboard** — auto-creates a Lovelace dashboard with a single
  **Kirk Hill SCADA** tab: a full-bleed animated single-line diagram of the
  farm — 8 turbines feeding the site collection bus, through the step-up
  transformer, into the national grid. It shows **Owner**, **Site** and
  **Return on investment** panels, live wind speed, active-turbine count,
  next-hour forecast, an API-status pill, and an alarm indicator for any
  turbine in a fault state. Click Owner, Site, Wind, National Grid or a
  turbine for ApexCharts history (6H–1Y) and detail modals, a labelled
  turbine activity swimlane — or click **Return on investment** for the money
  and its forms. Its colour scheme is amber for power/energy, cyan for wind
  speed, green for financial values.
- **Per-turbine statistics** — each of T1–T8 reports power, capacity factor,
  wind speed, state text, active status, and generation (today + all-time), with
  colour-coded status pills.
- **Interactive turbine map** — OpenStreetMap tiles were previously a separate
  Turbines tab; that standalone view was retired in v4.8.80 (the History tab
  was removed in v4.8.77 and the Finances tab in v4.8.79 — money now lives in
  the Return on investment panel). Turbine status, power, and generation
  today all live in the SCADA card. The standalone `kirkhill-wind-turbine-map`
  card is now **deprecated** (it shows a warning banner and will be removed in
  a future release).
- **Notifiable** — entities support a WhatsApp alert guide for turbine
  down/recovery.
- **Config flow & options** — masked API key entry, optional
  auto-dashboard, and
  configurable polling interval. Customisations and user-added cards are
  preserved across reloads and updates.

## Quick start

1. Add this repository to **HACS → Settings → Custom Repositories** as an integration.
2. Install **Kirk Hill Wind Farm**.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & Services → Add Integration → "Kirk Hill Wind Farm"**.
5. Enter your API key, choose whether to create the dashboard automatically,
   and set a site name.

> Generate your API key by logging in to the dashboard
> <https://dashboard.kirkhillcoop.org>, click your username in the top right,
> scroll to the API section, select **Generate**, and copy the key.
>
> **Dashboard sign-in is temporarily unavailable.** An upstream issue means
> keys issued by the sign-in flow are rejected by the API, so setup offers the
> API-key path only. The code stays in the integration and the option returns
> once the dashboard is fixed.

> Want to include earnings from the Ethex Investment Platform? Add
> <https://github.com/mjp-76/ha-ethex> too (experimental; awaiting Ethex go-live).

> Want to try a pre-release? See
> [Install a pre-release version](https://MJP-76.github.io/KirkHillWindFarm/installation/#install-a-pre-release-version).

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
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/KirkHillWindFarm/validate.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/validate.yml
[badge-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/KirkHillWindFarm/actions/workflows/ci.yml
[badge-release]: https://img.shields.io/github/v/release/MJP-76/KirkHillWindFarm?style=flat&label=Release
[releases]: https://github.com/MJP-76/KirkHillWindFarm/releases
[badge-built-with-ai]: https://img.shields.io/badge/Built%20with-AI-black?logo=openai&logoColor=white
[built-with-ai]: https://openai.com
[dashboard-yaml]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/dashboards/kirkhill_wind_scada.yaml
[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
