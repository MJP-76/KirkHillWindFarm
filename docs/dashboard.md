# Dashboard

When you add the integration, it can auto-create a Lovelace dashboard tab
(`kirk-hill-wind-dashboard`) in the sidebar.

## SCADA tab

The first tab: a full-bleed animated single-line diagram of the farm — 8
turbines feeding the site collection bus, through the step-up transformer, into
the national grid. Each turbine shows live power, colour-coded status, last
status time, today's generation and rotor speed; flow dots animate in proportion
to power. The national grid block shows **Owner and Site** export power and
to-grid-today side by side, the header shows live wind, active-turbine and
next-hour forecast chips. Rendered as a panel view so it fills the entire tab.

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

### Restored generation values

After a Home Assistant restart, generation figures (yesterday, today, week,
month, YTD, year, all time) are restored from the last known cached values
while waiting for the next API fetch. Restored values are shown at **50%
opacity** so you can distinguish them from live API reads. Once the integration
fetches fresh data, the opacity returns to normal.

### Chart timeframe control

A **"Chart timeframe"** bar sits at the top of the SCADA card, offering
**6H / 12H / 24H / 1W / 1M / 6M / 1Y** (24H default). The selected range drives
**every** modal chart (turbine, site, and owner alike) instead of a fixed 25-hour
window. Modal headings show the active range (e.g. "Historical Data (1W)").

### Site and Owner detail modals

Clicking the **Generation & Capacity** panel opens a dedicated detail modal for
the scope you clicked — a separate **Site** modal and a separate **Owner** modal,
each with its own ApexCharts series for the selected timeframe. The panels have a
cursor/hover affordance to signal they are clickable.

## Finances tab

- **Owner finances** projected timeframe value sensors
- **Site finances** projected timeframe value sensors

## History tab

- **Combined Power and Wind** history graph — owner power, site power, and wind speed on a single chart
- **Dual-axis Power chart** (ApexCharts) — site power (MW) and owner power (kW) on separate Y-axes
- **Power vs Wind scatter plot** (Plotly) — wind speed (m/s) vs site power (MW) correlation

## Turbines tab

- **Turbine activity history** — 24-hour active/inactive history for all 8 turbines
- **Interactive turbine map** — a full-width animated map card with:
  - T1–T8 labels above each turbine marker
  - Turbine icons that spin in proportion to live site capacity factor
  - Active/inactive state shown by marker colour
  - Running/stopped legend and per-turbine hover title
  - Fixed zoom level (15) centred on the farm
  - Scroll wheel zoom, drag-to-pan, pinch zoom, double-click/double-tap to reset
- Per-turbine owner/site power, state, and active status cards

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
