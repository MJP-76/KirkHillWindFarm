# Changelog

All notable changes to the Kirk Hill Wind Farm integration.

## Version 4.8.64 (stable)
- **Deprecated `via_device` replacement**: turbine devices now link to the farm
  hub via the resolved hub device registry id (`via_device_id`) instead of the
  deprecated `via_device=(DOMAIN, entry.entry_id)` identifier tuple. Resolved
  once per setup via `get_farm_device_id(hass, entry)` and stored on the
  coordinator. Required for Home Assistant Core 2027.8 compatibility (needs a
  full HA restart for the Python `custom_components/` change to take effect).
- **Global chart timeframe control**: a "Chart timeframe" bar at the top of the
  SCADA card (6H / 12H / 24H / 1W / 1M / 6M / 1Y, 24H default). All modal charts
  (turbine, site, owner) now honour the selected range instead of a fixed 25h
  window. Range is stored per-card and headings show the active range.
- **Separate Site and Owner detail modals**: the Generation & Capacity panel now
  opens a dedicated detail modal for the selected scope (site or owner) with its
  own ApexCharts 25h-series charts, split from the single combined modal.
- All v4.8.63 features preserved.

## Version 4.8.63 (stable)
- **Hide default ApexCharts legend** in turbine modal charts (no duplicate legend).
- **Relabel per-turbine timestamp to "Status since"** so it is not mistaken for
  stale data — the value is the time the current status began.
- **Fix wind-panel text overflow**: title 16px, value 18px so content stays inside
  its box on the SCADA card.
- All v4.8.62 features preserved.

## Version 4.8.62 (stable)
- **Turbine Power and Wind Speed charts as line graphs** instead of area charts.
- **Fix blank modal charts**: ApexCharts and history are now loaded via
  `hassUrl`/`callApi` (`history/period`) so turbine modal charts render.
- **Simplify shipped dashboard**: collapse the redundant 25h chart stack in the
  Overview Charts section.
- All v4.8.61 features preserved.

## Version 4.8.61 (stable)
- **ApexCharts error handling**: turbine detail modal now shows a visible fallback message if ApexCharts fails to load (e.g., on iOS), instead of silently rendering empty chart placeholders. Load errors and timeouts are now logged to the browser console for diagnosis.
- All v4.8.60 features preserved.

## Version 4.8.60 (stable)
- **Fix status text color**: status text fill now uses `style.fill` instead of `setAttribute("fill", ...)` so CSS `var()` resolves correctly — text now shows the saturated status color (green/blue/red) against the pastel pill background.
- All v4.8.59 features preserved.

## Version 4.8.59 (stable)
- **Pastel status pills**: pill backgrounds now use `color-mix(in srgb, <status-color> 15%, card-bg)` instead of a solid saturated fill — gives a soft, muted pastel tint that works in both light and dark themes. Status text fill is set to the full status color via JS so it contrasts cleanly against the pastel pill.
- All v4.8.58 features preserved.

## Version 4.8.58 (stable)
- **Fix black-on-black theme rendering**: the card's `:host` color aliases referenced `--ha-*`-prefixed tokens (`--ha-card-background`, `--ha-primary-color`, `--ha-primary-text-color`, etc.) that do not exist in Home Assistant's global theme scope, and v4.8.54 removed the inline fallbacks — so backgrounds resolved transparent (showing the black page behind) and text fell back to black. Aliases now read HA's real theme tokens (`--card-background-color`/`--paper-card-background-color`, `--primary-text-color`, `--secondary-text-color`, `--primary-color`, `--success-color`, `--error-color`, `--warning-color`, `--divider-color`) with readable fallbacks, verified in both light and dark themes. All `color-mix()` background tints updated to the same real tokens.
- All v4.8.57 features preserved.

## Version 4.8.57 (stable)
- **Fix render crash on all engines (including iOS/WebKit)**: status pill no longer writes `className` on its SVG `<rect>` (a read-only `SVGAnimatedString` getter — a guaranteed `TypeError` in strict mode). The pill class is now applied via `setAttribute("class", ...)`, so the card renders instead of throwing.
- **Drop cyclic `--ha-font-size-*` tokens**: the self-referential `:host` definitions (e.g. `--ha-font-size: var(--ha-font-size, 14px)`) are guaranteed-invalid at computed-value time and silently broke font inheritance inside the Shadow DOM; they are removed so theme font tokens flow through normally.
- **Restore font fallbacks**: every `font:` shorthand using `var(--ha-font-size-*)` now carries an inline px fallback (12/14/16/18/20/24px) so a missing theme token cannot invalidate the whole rule.
- All v4.8.56 features preserved.

## Version 4.8.56 (stable)
- **Arrow marker theme-aware**: flow arrow now uses `--khscada-accent-color` (maps to `--ha-primary-color`) instead of hardcoded blue.
- All v4.8.55 features preserved.

## Version 4.8.55 (stable)
- **All backgrounds theme-aware**: turbine boxes, bus bar, National Grid box, chips, panels, alarm, legend — all use HA semantic color variables (`--ha-card-background`, `--ha-primary-color`, `--ha-success-color`, `--ha-error-color`) via local `--khscada-*` aliases with `color-mix()` for subtle tints. No hardcoded hex colors remain.
- Status pills & legend dots now use HA variables (success/accent/warn/error/disabled) instead of hex.
- All v4.8.54 features preserved.

## Version 4.8.54 (stable)
- **Full theme-aware SCADA card**: all fonts, colors, and styles now use HA CSS variables (`--ha-font-size-*`, `--ha-primary-text-color`, `--ha-secondary-text-color`, `--ha-card-background`, `--ha-divider-color`, `--ha-primary-color`, etc.) with local `--khscada-*` aliases. No hardcoded colors or absolute px remain. The card now fully responds to dashboard themes, font-size settings, and custom HA themes.
- All v4.8.53 features preserved.

## Version 4.8.53 (stable)
- **Shadow DOM fix for HA font tokens**: added `:host` variable inheritance so `--ha-font-size-*` tokens now penetrate the card's Shadow DOM. Generation panels, turbine nodes, and all text now respond to HA's global font-size setting.
- All v4.8.52 features preserved.

## Version 4.8.52 (stable)
- **Full SCADA card uses HA native font tokens**: every text element now references `--ha-font-size-*` variables (small/large/xlarge/xxlarge/xxxlarge) instead of absolute px. The card now scales with the user's HA font-size setting and matches system hierarchy.
- Turbine nodes, transformer, chips, panels, alarm, legend, and modal all converted.
- All v4.8.51 features preserved.

## Version 4.8.51 (stable)
- **National Grid box uses HA native font tokens**: labels/units → `--ha-font-size-large` (16px), title/values → `--ha-font-size-xxlarge` (20px bold). Now scales with user's HA font-size setting and matches system hierarchy.
- All v4.8.50 features preserved.

## Version 4.8.50 (stable)
- **National Grid box fonts softened**: labels and units raised to 16px, values lowered to 20px bold (was 13/23), reducing the label/value size gap from 10px to 4px for a more balanced look. Title stays 20px bold.
- All v4.8.49 features preserved.

## Version 4.8.49 (stable)
- **National Grid box fonts aligned to the card-wide scale**: the box previously rendered every element at 22px (title, labels, values, units) — the only element that broke the size hierarchy. Title now bold 20px, labels 13px, values bold 23px and the "kWh" unit 13px, matching the Owner/Site/Wind panels exactly. Dead `.grid-col` rule removed.
- All v4.8.48 features preserved.

## Version 4.8.48 (stable)
- **Fix turbine detail modal charts showing no data**: the modal depends on ApexCharts, which was never loaded, so `_renderCharts` silently returned and every chart stayed empty. ApexCharts (v4.4.0) is now bundled with the integration and lazy-loaded the first time the modal opens.
- **"Active Turbines" pill compacted**: width 190 → 150, label 13px → 12px and value 14px → 13px so it no longer dominates the header row.
- **Re-center button now level with the legend**: the status legend's two lines are vertically centred in their block, matching the button's height.
- **National Grid box narrowed**: width 265 → 225 (right edge now at x1200 instead of the card edge). The Owner/Site panels re-align to the grid box's new right edge so the right column still lines up.

## Version 4.8.47 (stable)
- **Turbine staircase collapse**: the gap between the two turbine columns starts smaller (40 instead of 70). As the card narrows, the right-hand column now slides under the left one until it merges into a single column.
- **Gap between merged turbine boxes**: stacked boxes gain a small vertical gap as the columns merge, so they never touch once in single-column mode. Box height budget absorbs the gap so the block still clears the National Grid box.

## Version 4.8.46 (stable)
- **Re-center button moved out of the top-right corner**: now sits at the bottom-left, immediately left of the status legend and vertically centred against it (height matches the legend's two lines).
- **National Grid box now lines up with the Generation & Capacity panels**: the Owner and Site panels extend to the card's right edge (same right edge as the National Grid box), so the right-hand column aligns. Value columns moved to keep the same right padding.

## Version 4.8.45 (stable)
- **Fix Wind & Forecast panel overlap**: the panel now ends 8px before the National Grid bus line, so it no longer overlaps the transformer/bus bar.
- **Fix "Active Turbines" pill text overlap**: pill widened with label left-aligned and the "8 of 8" count right-aligned, so the label no longer collides with the value.
- **Fix turbine status pill overflow**: pill widened so longer statuses (e.g. `THERMAL FAULT`, `MAINTENANCE`, `UNAVAILABLE`) no longer spill outside the pill at narrower card widths.
- All v4.8.44 layout fixes preserved.

## Version 4.8.44 (pre-release)
- **Fix overlapping layout elements**: viewBox minimum height restored to 1052 (was incorrectly lowered to 860 in v4.8.42). At 860 the National Grid box (top at `H−460`) collided with the Site Generation & Capacity panel, and the status legend (`H−150`) overlapped the bottom turbines (T7/T8). With `hMin: 1052` the grid box sits below the panels and the legend clears the turbine block again.
- Card still bounded to the viewport (`calc(100vh - 64px)`) — the v4.8.43 fix is unchanged.

## Version 4.8.43 (stable)
- **SCADA card no longer inflates past the screen**: restores viewport-bounded sizing — `ha-card` capped at `calc(100vh - 64px)` with `:host` filling the grid cell, so the card always fits on-screen regardless of grid size. The v4.8.41 change to `height: 100%` let the grid inflate the card beyond the viewport; reverted to the v4.8.38 approach.
- All v4.8.40 features preserved: turbine detail modal, generation timeframes, mouse/pinch zoom, reset button, theme-aware ApexCharts.

## Version 4.8.42 (stable)
- **Fix vertical stretch**: VIEWBOX `hMin` changed 1052 → 860 (matches design height), `hMax` 1600 → 1200 (limits expansion).
- ResizeObserver derives the viewBox from the actual container aspect ratio.
- HA grid sizing via `getCardSize()`/`getGridOptions()`.
- All v4.8.40 features preserved.

## Version 4.8.40 (stable)
- **Turbine detail modal** with historical charts (Power, Wind vs Power, Capacity Factor, Rotor Speed, Wind Speed, Generation Today) — tap a turbine to open.
- **Generation & Capacity panels** with timeframe breakdowns (Yesterday, Today, Week, Month, YTD, Year, All time) for Owner and Site.
- **Wind & Forecast panel**.
- **Mouse wheel zoom + drag pan** for browser displays; pinch zoom + drag pan for touch devices.
- **Double-click / double-tap to reset zoom** and a reset zoom button (⟲).
- **Theme-aware ApexCharts** coloring.
- **Fixed**: removed forced heights that broke dashboard layouts — card uses HA grid sizing via `getCardSize()`/`getGridOptions()`. Supersedes the retracted v4.8.39 / v4.8.41–43 experiments.

## Version 4.8.38 (stable)
- **Wind panel moved left**, National Grid simplified, turbine ID/status aligned.

## Version 4.8.37 (pre-release)
- **Flow-dot speed proportional to line length + power**: energy-flow dots animate faster with higher power output, scaled by feed-line length.

## Version 4.8.36 (stable)
- **Fix SCADA card temporal-dead-zone crash**: `gridRectX` was read before its `const` declaration (introduced in v4.8.35.1), throwing `ReferenceError` and leaving the dashboard in a "configuration error" state.
- **Dashboard entity mapping fixes**: wind forecast → `open_meteo_next_hour_wind_speed_mps`, capacity factor scoped to site/owner entities, `async_load(False)`.
- Includes all v4.8.35.1 / v4.8.35.2 / v4.8.35.4 fixes.

## Version 4.8.35.4 (pre-release)
- **Fix dashboard creation race**: `_async_ensure_dashboard` re-fetches the dashboard item on `url_already_exists` (concurrent setup calls) and continues with merge/save instead of silently returning.
- **Empty turbines guard**: `_build_dashboard_config` falls back to T1–T8 with a debug log if no turbine entities are registered yet, preventing the SCADA card `setConfig()` from throwing.
- **Remove hardcoded entity IDs**: SCADA card config now uses `farm()`/`farm_scoped()` lookups for wind speed, wind forecast, active, alarm, and capacity factors — works with any site name and avoids `_2` suffix collisions.
- Includes all v4.8.35.2 / v4.8.35.1 fixes.

## Version 4.8.35.2 (pre-release)
- **Fix silent dashboard overwrite**: `_async_ensure_dashboard` logs a warning when loading the existing dashboard config fails, instead of silently overwriting user customizations with defaults.
- **Guard summary access in sensors**: farm active/inactive sensors use defensive `.get()` chains so a malformed/missing `summary` returns `unavailable` instead of raising `KeyError`.
- **Deduplicate `_owner_share_pct()`**: moved from `FarmPowerSensor` and `FarmGenerationByTimeframeSensor` to the shared `KirkHillScopedEntity` base class in `entity.py`.
- Includes all v4.8.35.1 changes.

## Version 4.8.35.1 (pre-release)
- **Font size increases** across all dashboard elements for readability: SCADA turbine details (11→14px), panels (17→20px), grid titles/values (20→22px), chips (11→14px), alarm (12→13px), turbine map labels (11→13px).
- Includes all v4.8.35 changes.

## Version 4.8.35 (pre-release)
- **Fully responsive SCADA card**: diagram now scales proportionally in both width and height to fit any container (mobile, panel view, side-by-side). ViewBox bounds 900–1800w × 1052–1600h. All coordinates derived from design width (1240) so layout stays intact at any size.
- **Flow arrow to grid box center**: energy-to-grid flow line and animated dot now terminate at the center of the National Grid box (halfway up) instead of the left edge.
- **Text/formatting polish**: Owner panel → "Capacity Factor (%)", "Your Share (W)", "Owner Capacity Factor (%)", "Share (‱)"; Site panel → "Site Capacity Factor (%)", "Site Power (MW)"; Wind panel → "Wind & Forecast", "Current Wind", "Forecast (1h)"; Grid → "To Grid Today". Finances tab headings title-cased. Turbine map legend spacing improved.
- **Bug fix**: `sitePowerText` reassignment changed from `const` to `let` (prevented card render in strict mode).

## Version 4.8.34 (pre-release)
- **Turbine staircase layout**: turbines now form a brick-wall staircase — T1 left, T2 right with its top level with T1's bottom, T3 left level with T2's bottom, and so on — so every feed line reaches the bus unobstructed. The block is spread to roughly match the bus bar height, and boxes are sized taller to leave room for more per-turbine details.

## Version 4.8.33 (pre-release)
- **Generation & capacity panel**: the top-right "Your generation" box is now "Generation & capacity" with separate lines for Generation (today), Percentage (owner capacity factor), Your share (live watts), Capacity (site capacity factor) and Share % (observed % of site generation today).
- **Wind & forecast panel**: wind speed and next-hour forecast now live in their own box directly below Generation & capacity (site capacity moved up into the panel above).

## Version 4.8.32 (pre-release)
- **Turbines staggered**: turbines are now arranged in two staggered columns (even on the left, odd on the right) instead of one tall column, so the turbine block fits in a much smaller top-to-bottom section.
- **Transformer label on the bus**: "TRANSFORMER" and "33 kV" now sit directly on the site collection bus bar (bigger, bold) instead of floating beside it.

## Version 4.8.31 (pre-release)
- **Simpler single-line diagram**: the separate transformer box is removed — "TRANSFORMER" now reads vertically down the site collection bus with a "33 kV" label, and the top "SITE COLLECTION BUS" wording is dropped. The National Grid box is moved up so its bottom edge lines up exactly with the bottom of the site collection bus, and the flow line enters the grid box there.

## Version 4.8.30 (pre-release)
- **Light theme**: the SCADA card now uses a light background (slate-100 shell, white panels) with dark slate text and slightly deeper accent colours (sky/blue bus, green grid, status pills unchanged), replacing the near-black navy background that was hard to read. Flow dots, arrows and hover highlights use a darker sky blue that stands out on light.

## Version 4.8.29 (pre-release)
- **Fix farm generation counters stuck on stale values**: the farm "generation today / yesterday / week / month / year / all-time" sensors were permanently frozen at the value restored on startup — the restored value took priority over live API data forever, so e.g. "Generation today" stopped updating after the first restart and showed yesterday's total. Live API data now takes priority, with the restored value used only as a placeholder until the first fetch after startup.

## Version 4.8.28 (pre-release)
- **Transformer and National Grid moved to the bottom**: the single-line diagram now reads turbines → bus → transformer → grid flowing down the card, with the transformer and National Grid box at the bottom (below the turbine stack) instead of the vertical centre

## Version 4.8.27 (pre-release)
- **Wind section uniform text**: "Current wind", "Forecast 1h" and "Site capacity" moved out of the small 11px chips into a proper "Wind & capacity" panel below "Your generation", now matching the same 20px size as the rest of the right-hand text

## Version 4.8.26 (pre-release)
- **Fix state class warning**: turbine "Generation today" sensors now use `state_class: total` (with `device_class: energy`) instead of `measurement`, matching the farm-level today sensor and Home Assistant's validation, so the "state class 'measurement' is impossible considering device class 'energy'" warnings are gone

## Version 4.8.25 (pre-release)
- **Uniform right-side text**: every label, value and unit in the National Grid box and the "Your Generation" panel now uses a single 20px size (bold for values/titles) instead of the previous mix of 11–27px, so the right-hand figures read as one consistent block

## Version 4.8.24 (pre-release)
- **Bigger right-side text**: National Grid box labels, values and units enlarged (title 16→20px, values 20–22→24–27px, labels/units 11→14px) and the top-right "Your Generation" panel enlarged, so both stay readable when the card is scaled down on phones
- **Owner export auto-derived**: when the API reports no owner power (owner share is tiny), the National Grid "Export" row now shows the owner export computed as site export × owner's share of today's generation (in W), instead of "—"; the "Your share" line uses the same value
- National Grid box now shows per-column units (owner export in W, site export in MW) and the "Export (MW)" row label is just "Export"

## Version 4.8.23 (pre-release)
- **National Grid "To grid today" figures fixed**: the SCADA card config was wired to the owner generation entity for both Owner and Site, so Site showed the owner's value (and Owner + Site looked identical). Site now resolves to the site generation entity via the entity registry (all other dashboard cards already did this; the SCADA card now matches).
- **Your share panel**: owner export power is now reported in watts (was mislabelled kW as W, off by 1000×, and rounded small values to "0 W")
- SCADA card now replaces (not duplicates) its stored copy on dashboard merge

## Version 4.8.22 (stable)
- **Turbine map mobile parity**: double-tap to reset the map view (matches the SCADA card, previously double-click only); legend hint updated to "Double-tap to reset"

## Version 4.8.21 (stable)
- **Mobile pinch-zoom and pan on the SCADA card**: two-finger pinch to zoom (up to 6x), one-finger drag to pan, double-tap to reset, `touch-action: none` so the browser does not hijack gestures
- Turbine tap still opens more-info on touch devices

## Version 4.8.20 (stable)
- **"Your Generation" panel moved to the far right** of the SCADA card (after the wind/forecast/capacity chips)

## Version 4.8.19 (stable)
- **SCADA entity IDs fixed**: use actual registry IDs (fixes missing data)
- **SCADA title removed** (saves space)
- **Your Generation panel** (top right): your generation (auto-scaled), last updated, your share in watts
- **Owner capacity factor** and **owner today generation** entities added to SCADA
- **Owner power fallback**: calculates from site power × owner share % when API returns 0/None

## Version 4.8.18 (stable)
- **Owner power fallback**: Calculates from site power × owner share % when API returns 0/None
- **SCADA "Your Generation" panel** (top right): your generation (auto-scaled), last updated timestamp, your share in watts
- **Owner capacity factor** and **owner today generation** entities added to SCADA

## Version 4.8.17 (stable)
- **Optimized API fetch tiers**: "yesterday" moved to slow tier (hourly) since it's static once the day ends; removed medium tier (week/month now also hourly); only "today" fetches every poll
- Reduces unnecessary API calls — yesterday/week/month/ytd/year/alltime now only fetch hourly

## Version 4.8.16 (stable)
- **State restoration for generation sensors**: farm and turbine generation sensors now restore their last known values on Home Assistant restart, avoiding "—" gaps while waiting for slow-tier API fetches
- Added `RestoreEntity` to `FarmGenerationByTimeframeSensor`, `TurbineGenerationTodaySensor`, `TurbineGenerationAlltimeSensor`

## Version 4.8.15 (stable)
- **Overview tab removed**: dashboard now starts with SCADA, then Finances, History, Turbines
- **Finances tab moved to second position** (after SCADA)
- **Obsolete view cleanup**: Overview view automatically removed from existing dashboards on merge

## Version 4.8.14 (stable)
- **Overview cleanup**: removed KPI row (Alarm tile, Reload button) and Site metrics card; Overview now shows only Owner/Site generation markdown cards
- **Finances tab fixed**: now shows generation kWh alongside projected earnings for all timeframes (Owner & Site), not just monetary values
- **Obsolete card/section cleanup**: removed cards/sections automatically pruned on dashboard merge

## Version 4.8.13 (stable)
- **SCADA dashboard redesign**: alarm + active turbines moved above turbine list (left), always-visible alarm chip (OK / flashing ALARM), cleaner National Grid box, renamed wind chips (Current Wind / Forecast 1h), new Site Capacity chip
- **Capacity Factor moved**: removed from Overview KPI row and Site metrics; added to SCADA dashboard as "Site Capacity"
- **Bus summary removed** (redundant with National Grid box)
- **Turbine status legend moved** to left side below turbine list
- **Dashboard customisation preserved** with factory reset options documented
