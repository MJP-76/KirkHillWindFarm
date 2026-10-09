# Installation

## Pre-requisites

Generate your Kirk Hill Wind Farm API key by logging in to the
[dashboard](https://dashboard.kirkhillcoop.org), click your username/account
in the top right corner, scroll down to the API section, press **Generate**
and copy the API key.

!!! note "Dashboard sign-in is temporarily unavailable"

    Setup offers the API-key path only. An upstream issue means the key issued
    by the sign-in flow is well formed (56 characters, `kh_live_…`) yet rejected
    by the API with `401 The API key is not valid.` — so sign-in is parked
    rather than offered as a dead end. The code and its tests stay in the
    integration; the option returns once the dashboard is fixed.

## Install via HACS

1. Add this repository to HACS (Custom Repositories)
2. Install **Kirk Hill Wind Farm**
3. Restart Home Assistant
4. Add the integration via **Settings → Devices & Services → Add Integration → Kirk Hill Wind Farm**
5. Enter your API key, choose whether to create the dashboard automatically,
   and set a site name

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

**v4.16.3** — see the
[changelog](https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md)
for what's included. The latest stable release is **v4.16.2**.

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

Then:

- **Create dashboard automatically** — whether the integration should create/update its Lovelace dashboard tab
- **Enable payment tracking onboarding (Ethex, experimental)** — optionally starts the Ethex setup flow
- **Site name** — used as the integration title in Home Assistant

If the dashboard stops accepting the key — for example after you revoke it —
Home Assistant asks you to enter a new one.

## Options

After setup, the **Configure** options let you change:

- Polling interval
- Create dashboard automatically
- Enable payment tracking onboarding (Ethex, experimental)

Prices are **not** options fields — they are `number` entities. **From v4.16.1
all three are disabled in the entity registry and set to `0.0`**:
`number.<farm>_owner_rate_p_w` (Owner rate, p/W — **what the Owner pill on the
card edits**), `number.<farm>_owner_price_p_kwh` (Owner price, p/kWh) and
`number.<farm>_negotiated_price_gbp_mwh` (Site/CfD price, £/MWh). The price
pills and the £ value column are still drawn but render **empty** (`Rate —`,
`—`) as a reminder that the model is unfinished (see [Sensors](sensors.md)).
Re-enable with `hab entity enable <entity_id>` once the board confirms how
member payments are calculated.

> **Note:** v4.11.7 removed the "projected annual earnings" setup fields. Those
> were estimated averages feeding a projected model retired in v4.11.5 — earnings
> are now live generation × real price, so the estimates were removed along with
> their number entities. Existing installations migrate automatically.
