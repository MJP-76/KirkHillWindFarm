# Installation

## Pre-requisites

Generate your Kirk Hill Wind Farm API key by logging in to the
[dashboard](https://dashboard.kirkhillcoop.org), clicking your username/account
in the top right corner, scrolling down to the API section, pressing
**Generate** and copying the API key.

## Install via HACS

1. Add this repository to HACS (Custom Repositories)
2. Install **Kirk Hill Wind Farm**
3. Restart Home Assistant
4. Add the integration via **Settings → Devices & Services → Add Integration → Kirk Hill Wind Farm**
5. Enter your API key, choose whether to create the dashboard automatically, and set a site name

!!! note "Ethex earnings"

    If you want to include your earnings from the Ethex Investment Platform,
    you will also need to add that repository
    [https://github.com/mjp-76/ha-ethex](https://github.com/mjp-76/ha-ethex).
    Payment onboarding is currently in testing, awaiting the go-live of Kirk
    Hill Wind Farm payments on Ethex.

The polling interval can be changed later from the integration's
**Configure** (Options) menu.

## Configuration

During setup, the integration asks for:

- **API key** — entered as a masked password field in Home Assistant
- **Create dashboard automatically** — whether the integration should create/update its Lovelace dashboard tab
- **Owner projected annual earnings (GBP)** — used to derive timeframe values (non-dynamic)
- **Site projected annual earnings (GBP)** — used to derive timeframe values (non-dynamic)
- **Enable payment tracking onboarding (Ethex, experimental)** — optionally starts the Ethex setup flow
- **Site name** — used as the integration title in Home Assistant

## Options

After setup, the **Configure** options let you change:

- Polling interval
- Create dashboard automatically
- Owner projected annual earnings (GBP)
- Site projected annual earnings (GBP)
- Enable payment tracking onboarding (Ethex, experimental)

The negotiated CfD price is **not** an options field — it is a `number` entity
(`number.<farm>_negotiated_price_gbp_mwh`) you set from the entity's controls.
When set above 0, the dashboard's £ value column switches from the projected
model to live actual-generation × price (see [Sensors](sensors.md)).
