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

## Install via HACS or Marketplace

Kirk Hill Wind Farm is listed in the **HACS default repository**, so there is
nothing to add by hand.

[![Open Marketplace repository on My Home Assistant](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=MJP-76&repository=KirkHillWindFarm&category=integration)

The button above uses [My Home Assistant](https://my.home-assistant.io) to open
this repository straight in the store on your own instance — the first click
only asks you to link your instance if you have not used a My link before.

1. Install **Kirk Hill Wind Farm** from your instance's store:
   - **Home Assistant 2026.11 and newer (Marketplace):** go to
     **Settings → Marketplace**, search for **Kirk Hill Wind Farm** and select
     **Install**. The first time, accept the Marketplace warning before
     installing.
   - **Earlier versions (HACS):** go to **HACS → Integrations**, search for
     **Kirk Hill Wind Farm** and select **Download**.
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services → Add Integration → Kirk Hill Wind Farm**
4. Enter your API key, choose whether to create the dashboard automatically,
   and set a site name

!!! note "Already installed from a custom repository?"

    Nothing to migrate. Both HACS and the Marketplace track this repository
    by its GitHub address, so once the default listing is picked up — at the
    next startup or catalog refresh, within about a day of the listing going
    live — the entry you already have is simply re-marked as default. Your
    installed version, pre-release setting, config entry and entities are
    untouched. Do not delete the repository entry or uninstall the
    integration: both would remove the files.

!!! note "Not showing up yet?"

    A new listing can take up to 8 hours to reach the store, and each instance
    refreshes its list at startup and every 6 hours after that. Until then:

    - **Marketplace:** **Settings → Marketplace → Add from link** and enter
      `https://github.com/MJP-76/KirkHillWindFarm` (requires connecting your
      GitHub account).
    - **HACS:** **HACS → Settings → Custom Repositories**, paste the same URL
      and pick **Integration**.

    Either way the result is identical, and it becomes the same entry once the
    listing arrives.

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

### 1. Offer pre-releases

**Home Assistant 2026.11 and newer (Marketplace):**

1. Open **Settings → Devices & Services → Marketplace**
2. Open the **Kirk Hill Wind Farm** repository device page
3. Enable the disabled **Pre-release** entity, then turn on its switch

**Earlier versions (HACS):**

1. Open **Settings → Devices & Services**
2. Open the **HACS** integration
3. Open **Kirk Hill Wind Farm**
4. In the **Diagnostics** section, switch on the disabled **Pre-release** item

### 2. Install a specific pre-release

**Home Assistant 2026.11 and newer (Marketplace):**

1. Open **Settings → Marketplace**
2. Search for **Kirk Hill Wind Farm** and open its repository page
3. Click the **⋮** (ellipsis) in the upper-right corner
4. Click **Install another version**
5. Select the pre-release from the list
6. Click **Install**
7. Restart Home Assistant

**Earlier versions (HACS):**

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

    Repeat step 2 and pick the newest **Latest** version — from the
    **Install another version** dialog (Marketplace) or the **Need a
    different version?** dropdown (HACS) — then restart Home Assistant.
    Switching the **Pre-release** switch back off stops the store offering
    pre-releases as updates.

## What's in the latest release

**v4.19.0** is the latest **stable** release: the forecast series — the
integration now takes its forecast from the wind farm's own API instead of
Open-Meteo, exposes the dashboard's P50/P75/P90 expectations, and reads the
generation forecast that was already arriving.

**v4.19.1** is the current **pre-release**: the SCADA card escapes
timestamps it cannot parse, and the site pop-out gains forecast &
expectation charts. To be offered it, turn on **Pre-release** (above). See
the [changelog](https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md)
for the full history.

## Reporting a pre-release problem

Pre-release problems are the most useful kind of feedback, and they are the
main reason pre-releases are published. If something looks wrong, breaks, or
does not behave as the docs describe,
[open an issue](https://github.com/MJP-76/KirkHillWindFarm/issues/new) and
include the details below.

- **What did you do?** — the steps you took to trigger the problem
- **What happened?** — the actual behaviour you saw
- **What did you expect?** — what should have happened instead
- **Store version** — the version shown on the HACS integration in the
  sidebar (Home Assistant 2026.10 and earlier); on 2026.11 and newer the
  Marketplace ships inside Home Assistant, so the next line covers it
- **Home Assistant version** — **Settings → System → Repairs** (top of the page)
- **Integration version** — the version shown on the **Kirk Hill Wind Farm**
  card in HACS, or the **Installed version** of its update entity under
  **Settings → Devices & Services → Marketplace**

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
- **Board figures source** — **`Repo file — board_announcements.yaml`** (default): entries in the shipped YAML are upserted into the ledger as board records on every setup. Or **`Manual entry only`**: the file is ignored and the card becomes the only writer

Prices are **not** options fields — they are `number` entities. **From v4.16.1
all three are disabled in the entity registry and set to `0.0`**:
`number.<farm>_owner_rate_p_w` (Owner rate, p/W — superseded by the payment
ledger, which holds a rate per declared period),
`number.<farm>_owner_price_p_kwh` (Owner price, p/kWh) and
`number.<farm>_negotiated_price_gbp_mwh` (Site/CfD price, £/MWh). **No card reads them any more**: the `Value (£)` column and the `£/h` cells
were removed from the Owner and Site panels — generation only there — and
money lives in the **Return on investment** panel (see [Sensors](sensors.md)).
Re-enable one with
`hab entity enable <entity_id>` if you want it for something else.

> **Note:** v4.11.7 removed the "projected annual earnings" setup fields. Those
> were estimated averages feeding a projected model retired in v4.11.5 — earnings
> are now live generation × real price, so the estimates were removed along with
> their number entities. Existing installations migrate automatically.
