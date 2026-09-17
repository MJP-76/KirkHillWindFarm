# Development decisions

Dated, one-line decisions with the reasoning behind them. This file is the
single place a future contributor (human or AI) can learn *why* the repository
is the way it is, without reconstructing intent from git history. User-facing
changes and version history live in the [`CHANGELOG`][changelog] and the docs;
this file is for internal constraints and trade-offs.

Nothing here is fixed forever — update an entry (or add a new one) whenever a
decision changes.

## Environment and production

- **2026-09-04 — This host (`172.16.1.2`) is production.** Editing the installed
  copy under `/homeassistant/custom_components/kirkhill_wind/` + reloading the
  config entry is an immediate production deploy. Dev is `172.16.1.3`. GitHub
  releases and HACS are for other users only and are not a gate for this box.
- **2026-09-04 — Any change under `custom_components/` needs a full HA restart.**
  There is no code reload. Do not restart without the owner's explicit go-ahead.
  Frontend JS (the SCADA card) can be hot-deployed via a config-entry reload and
  does not need a restart.

## Device registry

- **2026-09-04 — Turbines link to the farm hub via `via_device_id`, not the
  deprecated `via_device=(DOMAIN, entry.entry_id)` tuple.** The hub device id is
  resolved **once** during `async_setup_entry` in `__init__.py` via
  `get_farm_device_id(hass, entry)` (`async_get_or_create`) and stored on the
  coordinator, before platform setups are forwarded. Required for HA Core
  2027.8 compatibility.
- **2026-09-04 — The farm hub is a `SERVICE` device** (`entry_type=SERVICE`,
  identifiers `(DOMAIN, entry.entry_id)`); turbines are separate physical
  devices linked to it via `via_device_id`.

## Release and HACS

- **2026-09-04 — HACS reads GitHub Releases, not tags.** a tag alone is not
  enough for HACS to pick up an update. Always publish a GitHub Release for a
  version users are meant to install.
- **Version source of truth is the root `VERSION` file**, propagated by
  `scripts/version_sync.py` to `manifest.json` and `pyproject.toml`. See
  [release-management](release-management.md).

## Code health

- **2026-09-04 — Dead code and unused imports removed to satisfy ruff** in the
  validate workflow (F401 unused imports, F841 unused local variables, E501 line
  length). Removed: `owner_value_entities`, `site_value_entities`, `kpi_cards`
  in `__init__.py`, and unused imports in `coordinator.py` / `sensor.py`. All
  were confirmed unused (single occurrence each); no live references.

## Owner share and earnings figures

- **2026-09-04 — Owner share % is watt-based and derived from the API, not
  configured.** The share equals `owner capacity_watts / site capacity_watts`
  from `/api/v1/current`. Buying more watts raises it automatically. The old
  `owner_share_percent` config field was removed (config version 3 → 4) because
  a user-entered % would go stale and because the previous generation-ratio
  derivation was cached forever.
- **2026-09-04 — The projected annual earnings (GBP) are live-editable via
  `number` entities, not only config.** Owner and site projected-earnings are
  exposed as integration `number` entities seeded from the config entry, and
  the financial sensors read them live from the coordinator. Values persist
  across restarts (`RestoreEntity`), so a user can adjust figures without
  reconfiguring when new share/watt data becomes available.
- **2026-09-16 — A negotiated CfD price (GBP/MWh) switches the £ column to
  live-accurate calculation.** A `number` entity (`negotiated_price_gbp_mwh`)
  stores the negotiated price. When set (>0), each timeframe's £ value is
  `actual generation kWh ÷ 1000 × price`; when 0 or live kWh is unavailable it
  falls back to the projected model. The alltime timeframe keeps the fallback
  path because no historical price data exists — the projected model cannot be
  replaced there without price history.

## Dashboard consolidation

- **2026-09-16 — SCADA is the sole live dashboard; History, Finances and
  Turbines are consolidated.** History's 25h charts are covered by SCADA Owner/Site
  modals (6H–1Y). The Finances tab was retired in v4.8.79: its earnings figures
  (today, this month, YTD) now render as a per-timeframe **£ value column** inside
  the SCADA card's **Owner Capacity** and **Site Capacity** panels (both Owner and
  Site scopes), and the right-side panels gained a "Generation, Capacity &
  Earnings" heading. The Turbines tab was removed in v4.8.80: the standalone map
  and per-turbine status overview no longer ship — per-turbine power, status, and
  today's generation live on the SCADA diagram, per-turbine history in each
  pop-out, and the coordinates in the turbine modal link to Google Maps. Existing
  installs prune History, Finances and Turbines views via
  `_OBSOLETE_VIEW_PATHS` / `_OBSOLETE_CARD_KEYS` on merge.

## Deployment state

- **2026-09-17 — Production is aligned with the repository at `4.8.80`.**
  `CHANGELOG.md` is the authoritative version history. GitHub Releases/HACS are
  for other users; this host deploys from `origin/main` commits mirrored into
  `/homeassistant/custom_components/kirkhill_wind/`.

[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
