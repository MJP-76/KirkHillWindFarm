# Kirk Hill Wind Farm

Home Assistant custom integration for the Kirk Hill Community Wind Farm.

Connects to the Kirk Hill dashboard API using your personal API key and provides live sensors for the whole farm and each individual turbine.

## What you get

- **Farm sensors** — live power, capacity factor, wind speed, active/inactive turbine count, and alarm state
- **Generation sensors** — yesterday, today, week, month, year-to-date, year, and all-time totals for both your owner share and the whole site
- **Per-turbine sensors** — power (owner + site), capacity factor (owner + site), wind speed, state text, and active binary sensor for each of the 8 turbines
- **Auto-generated Lovelace dashboard** — created automatically during setup with an overview tab and a Turbines tab containing:
  - Active/inactive turbine count and alarm status
  - An **interactive turbine map** showing all 8 turbines with T1–T8 labels, live spin animation proportional to output, scroll/pinch zoom, drag-to-pan, and double-click to reset
  - Full per-turbine detail cards

## Requirements

- A Kirk Hill Co-op membership with API access
- Your personal Kirk Hill dashboard API key

> **Not affiliated with Kirk Hill Co-op.** This is an independent community integration.
