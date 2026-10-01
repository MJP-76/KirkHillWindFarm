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

## Install a pre-release version

Pre-releases are development builds published before a stable release. Install
one only if you want to test early, or you need a change that has not reached
the stable release yet.

### 1. Let HACS offer pre-releases

1. Open **Settings → Devices & Services**
2. Open the **HACS** integration
3. Open **Kirk Hill Wind Farm**
4. In the **Diagnostics** section, switch on the disabled **Pre-release** item

### 2. Download a specific pre-release

1. Open **HACS** from the sidebar
2. Find **Kirk Hill Wind Farm**
3. Click the **⋮** (ellipsis) next to the integration
4. Click **Update information**
5. Click **Re-download**
6. Open the **Need a different version?** dropdown
7. Select the latest pre-release from the list
8. Restart Home Assistant

!!! warning "Pre-releases are development builds"

    They can contain incomplete or breaking work. Your existing config entry
    and entities are kept, but new sensors, renamed entities or removed
    options may appear. Check the
    [changelog](changelog.md) for what changed before installing.

!!! tip "Going back to a stable release"

    Repeat the steps above and pick the newest **Latest** version from the
    **Need a different version?** dropdown, then restart Home Assistant.
    Switching the **Pre-release** diagnostic back off stops HACS offering
    pre-releases as updates.

## What's in the latest pre-release

**v4.13.1** (pre-release) — released 2026-10-01

New diagnostic sensors:

- `binary_sensor.data_complete` — on when every turbine has current data
- `sensor.data_generated_at` — when the API response was generated
- `sensor.unknown_turbines` — turbines with no imported state
- `sensor.latest_import_status` — data import pipeline health
- Rotor speed `sampled_at` attribute — when rotor speed was last measured

Performance improvements:

- Removed redundant `/api/v1/wind-speed` API call (saves 6 calls/hour)
- Cached immutable year summaries — completed years fetched once (saves 4 calls/hour)
- Open-Meteo forecast now runs in parallel with timeframe summaries

Other changes:

- Dashboard `url_already_exists` detection hardened against HA translation changes
- Docs: sensor reference, SUPPORT, CONTRIBUTING files added
- Test fix: flaky `test_obsolete_card_removed` now deterministic

[Full changelog](https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md)

## Reporting a pre-release problem

Pre-release problems are the most useful kind of feedback, and they are the
main reason pre-releases are published. If something looks wrong, breaks, or
does not behave as the docs describe,
[open an issue](https://github.com/MJP-76/KirkHillWindFarm/issues/new) and
include the details below.

- **What did you do?** — the steps you took to trigger the problem
- **What happened?** — the actual behaviour you saw
- **What did you expect?** — what should have happened instead
- **HACS version** — the version shown on the integration in the HACS sidebar
- **Home Assistant version** — **Settings → System → Repairs** (top of the page)
- **Integration version** — the version shown on the **Kirk Hill Wind Farm** card in HACS

State which pre-release you are on — version numbers like `v4.13.1` are more
precise than "the latest".

If a problem makes the integration unusable, follow the
[going back to a stable release](installation.md#install-a-pre-release-version)
steps above first, then report it.

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
