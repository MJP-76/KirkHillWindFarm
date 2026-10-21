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

!!! note "Money lives on its own card"
    **2026-10-09** — the £ column, the £/h cells, the price pills and the
    member-savings line were switched off while the model was confirmed, and
    deliberately left drawn-but-empty as a standing reminder.

    **2026-10-21 — removed outright.** All money now lives on the **Return on
    investment** card below; the SCADA card shows generation, power, capacity
    and wind only, on both the Owner and Site panels. The 22 earnings entities
    stay disabled and zeroed, and nothing on the SCADA card reads them.

### Return on investment (its own view, path `roi`)

`custom:kirkhill-wind-roi` is the single place financial figures appear:

- **Header** — the **invested amount** (click to set it; stored in the ledger's
  Store, never `entry.options`) beside four stats: **Declared total**,
  **Board announced**, **Self estimated** and **Return**.
- **Rows** — one per declared period, e.g.
  `Feb 2025 – Jun 2026 · 21 p/W × 2,559 W · £537.49 · ROI 10.75%`, each with
  edit and remove, plus **Add period**.
- **Return is a plain percentage of capital**: `value ÷ invested × 100` per
  period and the same across the total. It is deliberately **not annualised** —
  the board pays per period regardless of how long it runs, so a per-year figure
  would be a rate of our own invention. With no capital entered the ROI reads
  `—`, never `0%`.
- **A caption under the rows** says which of three things the current period is:
  board-declared, your own estimate, or an estimate awaiting the board
  (`~£537.49`, priced from the last announced rate).
- **Adding a period opens prefilled** with the month after the latest one ends —
  Feb 2025 → Jun 2026 offers **`2026-07`** — and the end month left blank, since
  when the board's next period closes is not ours to guess.

#### The ledger behind it

- **Each line item is a run of whole months plus the rate** —
  `{start month, end month, rate p/W, watts owned, note, source}`. The figure
  for a line is `watts × p/W ÷ 100`; the period only says *which* declaration
  applies, never how long money accrues for. A period is stored as the **1st to
  the last day** of its months, so "Feb 2025 – Jun 2026" means exactly those
  months whatever dates were picked.
- **`source` is `board` or `self`.** The form's *Board announced* box is
  pre-ticked; untick it to record your own estimate for a period the board has
  not declared. Records predating the field normalise to `board`. The total
  still sums both, `board_total_gbp` / `self_total_gbp` say how much of it was
  announced, self rows are dashed, tagged and `~`-prefixed, and **only board
  records feed the published rate** — a self estimate is not a published figure.
- **Storage and writes** — one Store file per config entry (never
  `entry.options`: config-entry migrations purge monetary keys there). Changed
  only through `kirkhill_wind.add_payment_record`, `update_payment_record`,
  `remove_payment_record` and `set_invested_amount`; the card never writes
  storage itself.
- **`sensor.<farm>_payment_ledger`** exposes `records` (each with `value_gbp`
  and `roi_pct`), `total_gbp`, `board_total_gbp`, `self_total_gbp`,
  `invested_gbp`, `total_roi_pct`, `latest_rate_p_per_w`,
  `latest_board_rate_p_per_w`, `current_gbp`, `current_basis`,
  `current_source`, `current_year_gbp` and `year_totals_gbp`.

### What the SCADA card no longer shows

- Gone from both panels: the **`Value (£)` column**, the **`£/h`** cells, the
  **Member savings** line and both **price pills** (Owner and Site). Generation
  now takes the right-hand edge of each panel instead of leaving the old money
  column's gap.
- **The timeframe rows stay moneyless on purpose.** `Yesterday … Year` are
  `kWh × price` sensors that remain disabled, and slicing a per-watt
  declaration across days would be the accrual the board's basis rules out —
  see [Development decisions](development/decisions.md). The ledger still
  exposes `current_year_gbp` / `year_totals_gbp` (declarations attributed whole
  to the year they *end* in) for templates.

### Prices and member savings (entities present, disabled, unused by the cards)

`number.<farm>_owner_rate_p_w`, `number.<farm>_owner_price_p_kwh`,
`number.<farm>_negotiated_price_gbp_mwh` and
`sensor.<farm>_member_savings_value` still exist, **disabled and set to
`0.0`**. They feed no card any more: rates live per declared period in the
ledger. Re-enable one with `hab entity enable <entity_id>` if you want it for
something else — nothing on either card will change. The suppression rule for
valuing history as `kWh × today's price` still stands for those sensors
themselves (see [Sensors](sensors.md)).

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
