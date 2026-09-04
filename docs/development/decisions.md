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

## Deployment state

- **2026-09-04 — Production manifest is one release behind the repository**
  (prod `4.8.63`, repo/`VERSION` `4.8.65`). The frontend is live in prod
  (SCADA JS byte-identical to the repo); the Python changes are staged but not
  active until the pending full restart. `CHANGELOG.md` is the authoritative
  version history.

[changelog]: https://github.com/MJP-76/KirkHillWindFarm/blob/main/CHANGELOG.md
