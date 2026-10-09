# Dashboard

When you add the integration, it can auto-create a Lovelace dashboard tab
(`kirk-hill-wind-dashboard`) in the sidebar.

## Kirk Hill SCADA tab

The first (and, since v4.8.80, only) tab — titled **Kirk Hill SCADA**: a
full-bleed animated single-line diagram of the farm — 8
turbines feeding the site collection bus, through the step-up transformer, into
the national grid. Each turbine shows live power, colour-coded status, last
status time, today's generation and rotor speed; flow dots animate in proportion
to power. The national grid block shows **Owner and Site** export power and
to-grid-today side by side, the header shows live wind, active-turbine and
next-hour forecast chips. Your **share of bought watts** is shown in per-myriad
(‱) form (e.g. `1.36‱`) via the owner-share entity, falling back to the observed
generation ratio if that entity is unavailable. Rendered as a panel view so it
fills the entire tab.

### Alarm indicator

The **alarm indicator** (top-left of the SCADA card) shows one of two states:

- **OK** — no turbines are in a fault state. This includes normal operational
  states such as curtailment, no-wind stops, maintenance, and scheduled stops.
  These are not faults.
- **N FAULTS** (flashing red) — one or more turbines have a thermal or
  electrical fault (`status_category` of `fault_thermal` or `fault_electrical`).

### Turbine status pills

Each **turbine status pill** (on the turbine node) shows the individual
turbine's operational state: RUNNING, READY, STARTING, CURTAILED, NO WIND,
STOPPED, MAINTENANCE, UNAVAILABLE, or a fault label. The pill background is a
pastel tint of the status colour; the text is the saturated status colour.

A turbine can be **curtailed** (bird/bat protection, grid constraint, etc.)
while the alarm indicator still reads **OK** — curtailment is not a fault.

### API status pill

Bottom of the SCADA card, next to the version number (above the legend, on the
same line as the reload button). Reflects the coordinator's last fetch directly,
so an API outage is obvious rather than a page full of unknown values:

- **API OK** (green) — the Kirk Hill API last responded normally.
- **API DOWN** (red) — the coordinator's last fetch failed (timeout,
  rate-limit, or outage).
- **API —** — the status entity is unavailable or not configured.

### Restored generation values

After a Home Assistant restart, generation figures (yesterday, today, week,
month, YTD, year, all time) are restored from the last known cached values
while waiting for the next API fetch. Restored values are shown at **50%
opacity** so you can distinguish them from live API reads. Once the integration
fetches fresh data, the opacity returns to normal.

### Per-pop-out chart timeframe control

Each **Owner** and **Site** detail modal (and every turbine pop-out) has its own
timeframe selector offering **6H / 12H / 24H / 1W / 1M / 6M / 1Y** (24H
default). The selected range is remembered per pop-out type (owner, site,
turbine) and drives that modal's charts independently — there is no single
global timeframe control. Modal headings show the active range (e.g.
"Historical Data (1W)"). Windows longer than a week (1M / 6M / 1Y) use hourly
recorder statistics rather than raw history, so the charts stay usable on
slower browsers.

### Site, Owner and Wind detail modals

Clicking a **Capacity** panel (Owner or Site) opens a dedicated detail modal for
the scope you clicked — a separate **Site** modal and a separate **Owner** modal,
each with its own ApexCharts series for the selected timeframe. Clicking the
**Wind** panel opens a **Wind Speed** modal showing current wind speed, the
one-hour forecast, and the live difference. All clickable panels have a
cursor/hover affordance to signal they are clickable.

### Turbine detail modal

Clicking a turbine node opens its pop-out. Besides power, wind, rotor, capacity
and generation charts for the selected timeframe, the modal includes a
**turbine activity swimlane** — one labelled row per state the turbine was in
during the window (running, curtailed, in maintenance, stopped, in a fault
state, etc.) with a coloured block for each continuous stretch, so state changes
and their durations read at a glance. Hovering a block shows its start/stop time
and duration.

## Financials (formerly the Finances tab)

!!! warning "Earnings hidden pending the board's model"
    **2026-10-09** — every money figure on this card is hidden until the board
    confirms how member payments are calculated: the **`Value (£)` column, both
    live `£/h` rates, both price pills and the member-savings line are no longer
    rendered**, all 22 earnings entities are **disabled** in the entity registry,
    and all three inputs (`owner_price_p_kwh`, `owner_rate_p_w`,
    `negotiated_price_gbp_mwh`) are `0.0`. Restoring is `hab entity enable` plus
    re-adding the markup — nothing was deleted. See
    [Development decisions](development/decisions.md).

The standalone **Finances tab was removed in v4.8.79** — its content (today's
earnings, this month, year to date) now lives in the SCADA card itself. Every
timeframe row (Yesterday, Today, Week, Month, YTD, Year, All time) in both the
**Owner Capacity** and **Site Capacity** panels is built to show a **£ value
column** alongside the kWh figure, so generation and its value sit on the same
row. **At present that column is not drawn**, and the card shows energy only.

The **All time** kWh figure is **calculated as the sum of the per-year
sensors** — `2024 + 2025 + … + the current year to date`, including any future
years as they complete. The per-year figures themselves are sensors only
(`Generation (2024)`, `Generation (2025)`, …) and are **not shown on the card**;
see [Sensors](sensors.md).

### Prices (entities present, currently disabled)

Two independent price entities drive the £ figures:

- `number.<farm>_owner_price_p_kwh` — **Owner price in p/kWh** (enter `6` for
  6 pence). Drives the Owner panel's £ column and the owner £/h rate.
- `number.<farm>_negotiated_price_gbp_mwh` — **Site/CfD price in £/MWh**
  (CfD-style strike price). Drives the Site panel's £ column and the site £/h
  rate.

Both default to `0.0`, in which case the sensors read `£0.00` rather than a
projected figure. Displayed prices never round up (`0.06` shows as `0.06`), and
the Power rows can show a live £/h rate (`ownerExportKw × price` /
`sitePowerMw × price`) once a price is set.

**All of that is switched off:** both entities are disabled in the registry,
both sit at `0.0`, and the card no longer renders the price pills or the £/h
rates. They remain in the codebase so restoring them needs no reinstall.

### Member savings (per watt) — hidden

Members are paid for the watts they **own**, not for kilowatt-hours
generated. `sensor.<farm>_member_savings_value` computes
`owned watts × rate ÷ 100` from `number.<farm>_owner_rate_p_w` — at 2,559.465 W
and 21p/W that is **£537.49**, the figure the web dashboard reports for
Feb 2025–Jun 2026.

**The card line that displayed it has been removed**, and both entities are
disabled with the rate set to `0.0`, as part of the back-out above.

It has **no timeframe and does not accrue**: the board declares a payment when
its finances allow, and the board's "15p per watt per 12 months" is an
equivalence for one declaration rather than a rate to divide over time. How
`All time` should accumulate across declared periods is one of the open
questions — see [Development decisions](development/decisions.md).

### Suppressed £ values (All time)

The **All time** row always shows `—` in the £ column, regardless of price. The
API records energy only, never money, so this figure would be today's price
applied retroactively to history — misleading if the CfD price has ever changed.
The kWh figure on that row stays live (as the per-year sum). The past-year value
sensors follow the same rule. This is a standing decision pending confirmation
of the CfD strike price value(s), whether the CfD has changed, and its contract
length (see [Development decisions](development/decisions.md)). Once the CfD
history is known, each year gets its own price — the per-year sensors are the
foundation for the multi-CfD price schedule.

## History tab

**Removed in v4.8.77.** The 25-hour owner/site power and wind charts it held
are covered by the SCADA card's Owner and Site pop-out modals, which offer
selectable 6H–1Y timeframes. Data previously here is available through those
modals; the dedicated tab no longer exists.

## Turbines tab

**Removed in v4.8.80.** The standalone Turbines view (turbine map and per-turbine
status overview) has been deleted. Live per-turbine status, power, and generation
today are shown on the SCADA diagram, and per-turbine history is available through
each turbine's pop-out modal. Dashboards with the old `turbines` view are pruned
automatically on merge.

The standalone **turbine map card** (`kirkhill-wind-turbine-map`) is still
bundled so any manual placements keep rendering, but it is **deprecated** as of
v4.8.81: it shows a warning banner at the top of the card and will be removed in
a future release. Use the **Kirk Hill SCADA** card instead.

The turbine map card previously provided:
- T1–T8 labels above each turbine marker
- Turbine icons that spin in proportion to live site capacity factor
- Active/inactive state shown by marker colour
- Running/stopped legend and per-turbine hover title
- Fixed zoom level (15) centred on the farm
- Scroll wheel zoom, drag-to-pan, pinch zoom, double-click/double-tap to reset
- Tiles served by **OpenStreetMap** (standard tile URL `tile.openstreetmap.org/{z}/{x}/{y}.png`); the map previously used CARTO Voyager tiles (v4.8.76–v4.8.78) but has been reverted to OSM for reliability on all networks

The per-turbine status cards and the all-turbine activity graph were removed in
v4.8.77 — turbine power, status, and activity history are now shown on the SCADA
diagram and via each turbine's pop-out modal.

## Dashboard customisation

User-added cards, sections, and views are **preserved** across integration
reloads and updates. The integration only updates the cards it manages —
anything you add yourself is kept, and removed default cards are pruned without
touching your additions.

## Factory reset the dashboard

Your customisations stay until you **explicitly** wipe them. There are two ways
to start over:

**Option 1 — untick and rebuild from the integration**

1. Go to **Settings → Devices & Services → Kirk Hill Wind Farm → Configure**.
2. **Untick "Create dashboard automatically"** and save — the integration stops managing the dashboard, so nothing can be overwritten.
3. In the dashboard editor, **delete the `Kirk Hill Wind Farm` tab**.
4. **Re-tick "Create dashboard automatically"** (or reload the integration) — a fresh default dashboard is generated.

**Option 2 — reset immediately**

Call the `kirkhill_wind.reset_dashboard` service:

```yaml
service: kirkhill_wind.reset_dashboard
```

This restores the dashboard to the integration defaults and **discards all
customisations**.

## Bundled chart cards

The ApexCharts and Plotly Lovelace cards are bundled with the integration and
registered automatically. No separate HACS installation is required for the
dashboard charts.

## Frontend cards

The animated SCADA card, turbine map card, and chart cards are bundled by the
integration and loaded automatically with the dashboard. The frontend cards are
reloaded automatically whenever the integration starts or is reloaded — no
manual page refresh or HA restart required.

For manual import or customization, a dashboard YAML is also provided at
[`dashboards/kirkhill_wind_scada.yaml`][dashboard-yaml].

[dashboard-yaml]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/dashboards/kirkhill_wind_scada.yaml
