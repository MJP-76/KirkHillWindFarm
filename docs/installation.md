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
- **Enable payment tracking onboarding (Ethex, experimental)** — optionally starts the Ethex setup flow
- **Site name** — used as the integration title in Home Assistant

## Options

After setup, the **Configure** options let you change:

- Polling interval
- Create dashboard automatically
- Enable payment tracking onboarding (Ethex, experimental)

Prices are **not** options fields — they are `number` entities you set from the
entity's controls or the dashboard's price pills:
`number.<farm>_owner_price_p_kwh` (Owner price, p/kWh) and
`number.<farm>_negotiated_price_gbp_mwh` (Site/CfD price, £/MWh). When a price
is above 0, the dashboard's £ value column shows actual generation × price;
when it is 0 the sensors read `£0.00` (see [Sensors](sensors.md)).

> **Note:** v4.11.7 removed the "projected annual earnings" setup fields. Those
> were estimated averages feeding a projected model retired in v4.11.5 — earnings
> are now live generation × real price, so the estimates were removed along with
> their number entities. Existing installations migrate automatically.
