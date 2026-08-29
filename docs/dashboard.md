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
next-hour forecast chips, and a **flashing ALARM indicator** appears while the
farm alarm is on. Rendered as a panel view so it fills the entire tab.

A compact top-level **icon-only reload control** calls
`kirkhill_wind.reload_integration`.

## Overview

- Owner and site overview sections
- Dashboard range controls aligned with the Kirk Hill dashboard UX (`Today`, `Yesterday`, `7 days`, `30 days`, `year`, `All time`)
- Owner and site generation cards shown first in each overview section
- Owner generation cards show actual generation energy values with automatic unit scaling (kWh, MWh, GWh, TWh, PWh, EWh)
- Live farm wind and turbine availability

## Finances tab

- **Owner finances** projected timeframe value sensors
- **Site finances** projected timeframe value sensors

## History tab

- **Combined Power and Wind** history graph — owner power, site power, and wind speed on a single chart
- **Dual-axis Power chart** (ApexCharts) — site power (MW) and owner power (kW) on separate Y-axes
- **Power vs Wind scatter plot** (Plotly) — wind speed (m/s) vs site power (MW) correlation

## Turbines tab

- **Turbine status overview** card — active turbines, inactive turbines, and alarm state
- **Interactive turbine map** — a full-width animated map card with:
  - T1–T8 labels above each turbine marker
  - Turbine icons that spin in proportion to live site capacity factor
  - Active/inactive state shown by marker colour
  - Running/stopped legend and per-turbine hover title
  - Fixed zoom level (15) centred on the farm
  - Scroll wheel zoom, drag-to-pan, pinch zoom, double-click/double-tap to reset
- Per-turbine owner/site power, capacity, wind, state, and active status cards

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

The animated map card and chart cards are bundled by the integration and loaded
automatically with the dashboard. From **v4.5.2**, the dashboard and frontend
cards are reloaded automatically whenever the integration starts or is reloaded
— no manual page refresh or HA restart required.

For manual import or customization, a dashboard YAML is also provided at
[`dashboards/kirkhill_wind_scada.yaml`][dashboard-yaml].

[dashboard-yaml]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/dashboards/kirkhill_wind_scada.yaml