"""The Kirk Hill Wind Farm integration."""
from __future__ import annotations

import copy
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import (
    CONF_ICON,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    LOVELACE_DATA,
)
from homeassistant.components.lovelace import dashboard as lovelace_dashboard
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_GRAPH_HOURS,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_GRAPH_HOURS,
    PLATFORMS,
)
from .coordinator import KirkHillWindCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)
_FRONTEND_DIR = Path(__file__).parent / "frontend"
_FRONTEND_REGISTERED = "kirkhill_wind_frontend_registered"
_ETHEX_DOMAIN = "ethex"

_FRONTEND_CARDS: list[tuple[str, Path]] = [
    ("/kirkhill_wind/turbine-map-card.js", _FRONTEND_DIR / "kirkhill-wind-turbine-map.js"),
    ("/kirkhill_wind/apexcharts-card.js", _FRONTEND_DIR / "apexcharts-card.js"),
    ("/kirkhill_wind/plotly-graph-card.js", _FRONTEND_DIR / "plotly-graph-card.js"),
    ("/kirkhill_wind/scada-card.js", _FRONTEND_DIR / "kirkhill-wind-scada-card.js"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kirk Hill Wind Farm from a config entry."""
    coordinator = KirkHillWindCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_setup_payment_tracking(hass, entry)
    await _async_register_frontend(hass)
    await _async_ensure_dashboard(hass, entry)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-apply scan interval when options change."""
    coordinator: KirkHillWindCoordinator = entry.runtime_data
    coordinator.apply_options()
    await coordinator.async_request_refresh()
    await _async_setup_payment_tracking(hass, entry)
    await _async_ensure_dashboard(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry.runtime_data = None
        await async_unload_services(hass)

    return unload_ok


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register bundled custom Lovelace cards (turbine map, ApexCharts, Plotly)."""
    if not hass.data.get(_FRONTEND_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(url, str(path), False)
                for url, path in _FRONTEND_CARDS
            ]
        )
        hass.data[_FRONTEND_REGISTERED] = True

    # Always (re-)add the versioned URLs so the browser picks up JS changes
    # after an integration reload without needing a full HA restart.
    for url, path in _FRONTEND_CARDS:
        js_version = int(path.stat().st_mtime)
        add_extra_js_url(hass, f"{url}?v={js_version}")


async def _async_ensure_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create and register a Lovelace dashboard tab for this integration."""
    if LOVELACE_DATA not in hass.data:
        _LOGGER.debug("Lovelace not loaded yet; skipping dashboard auto-create")
        return

    if not _dashboard_enabled(entry):
        _LOGGER.debug("Dashboard creation disabled for config entry %s", entry.entry_id)
        return

    url_path = "kirk-hill-wind-dashboard"
    title = "Kirk Hill Wind Farm"
    icon = "mdi:wind-turbine"

    dashboards_collection = lovelace_dashboard.DashboardsCollection(hass)
    await dashboards_collection.async_load()

    item = next(
        (
            existing
            for existing in dashboards_collection.async_items()
            if existing.get(CONF_URL_PATH) == url_path
        ),
        None,
    )
    if item is None:
        try:
            item = await dashboards_collection.async_create_item(
                {
                    CONF_ICON: icon,
                    CONF_TITLE: title,
                    CONF_URL_PATH: url_path,
                    CONF_SHOW_IN_SIDEBAR: True,
                    CONF_REQUIRE_ADMIN: False,
                }
            )
        except (HomeAssistantError, vol.Invalid) as err:
            _LOGGER.warning("Failed to create Lovelace dashboard: %s", err)
            return

    lovelace_store = hass.data[LOVELACE_DATA].dashboards.get(url_path)
    if lovelace_store is None:
        lovelace_store = lovelace_dashboard.LovelaceStorage(hass, item)
        hass.data[LOVELACE_DATA].dashboards[url_path] = lovelace_store

    new_default = _build_dashboard_config(hass, entry)
    try:
        existing_config = await lovelace_store.async_load()
    except Exception:  # noqa: BLE001
        existing_config = None

    if existing_config and "views" in existing_config:
        config_to_save = _merge_dashboard_config(existing_config, new_default)
        _LOGGER.debug("Merged dashboard config with existing user customisations")
    else:
        config_to_save = new_default
        _LOGGER.debug("No existing dashboard found; saving default config")

    await lovelace_store.async_save(config_to_save)

    # Notify all connected browser clients that the dashboard config has changed
    # so they reload it without needing a manual page refresh.
    hass.bus.async_fire("lovelace_updated", {"url_path": url_path, "updated": True})

    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        frontend_url_path=url_path,
        require_admin=item[CONF_REQUIRE_ADMIN],
        show_in_sidebar=item[CONF_SHOW_IN_SIDEBAR],
        sidebar_title=item[CONF_TITLE],
        sidebar_icon=item.get(CONF_ICON, icon),
        config={"mode": "storage"},
        update=True,
    )


def _dashboard_enabled(entry: ConfigEntry) -> bool:
    """Return whether dashboard creation is enabled for this config entry."""
    return entry.options.get(
        CONF_CREATE_DASHBOARD,
        entry.data.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD),
    )


async def async_reset_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reset the Lovelace dashboard to defaults, discarding user customisations."""
    url_path = "kirk-hill-wind-dashboard"

    lovelace_store = hass.data.get(LOVELACE_DATA, {}).dashboards.get(url_path)
    if lovelace_store is None:
        _LOGGER.warning("Dashboard store not found; cannot reset")
        return

    new_default = _build_dashboard_config(hass, entry)
    await lovelace_store.async_save(new_default)
    hass.bus.async_fire("lovelace_updated", {"url_path": url_path, "updated": True})
    _LOGGER.info("Dashboard reset to defaults")


async def _async_setup_payment_tracking(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Initialize Ethex config flow when payment tracking is enabled."""
    if not entry.options.get(
        CONF_ENABLE_PAYMENT_TRACKING,
        entry.data.get(CONF_ENABLE_PAYMENT_TRACKING, DEFAULT_ENABLE_PAYMENT_TRACKING),
    ):
        return

    if _ETHEX_DOMAIN not in hass.config.components:
        _LOGGER.warning(
            "Payment tracking is enabled, but the Ethex integration is not installed."
        )
        return

    if hass.config_entries.async_entries(_ETHEX_DOMAIN):
        return

    _LOGGER.info("Payment tracking enabled: starting Ethex configuration flow")
    await hass.config_entries.flow.async_init(
        _ETHEX_DOMAIN,
        context={"source": "user"},
    )


def _entity_ids_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Return a map of entity unique_id to current entity_id."""
    registry = er.async_get(hass)
    entity_ids: dict[str, str] = {}

    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id:
            entity_ids[entity_entry.unique_id] = entity_entry.entity_id

    return entity_ids


def _generation_markdown_line(label: str, entity_id: str) -> str:
    """Return a markdown line that formats generation with scaled energy units."""
    return (
        f"- **{label}:** "
        f"{{% set v = state_attr('{entity_id}', 'raw_generation_kwh') %}}"
        "{% if v is not none %}"
        "{% set n = v | float(0) %}"
        "{% if n >= 1000000000000000 %}{{ '%.2f' | format(n / 1000000000000000) }} EWh"
        "{% elif n >= 1000000000000 %}{{ '%.2f' | format(n / 1000000000000) }} PWh"
        "{% elif n >= 1000000000 %}{{ '%.2f' | format(n / 1000000000) }} TWh"
        "{% elif n >= 1000000 %}{{ '%.2f' | format(n / 1000000) }} GWh"
        "{% elif n >= 1000 %}{{ '%.2f' | format(n / 1000) }} MWh"
        "{% else %}{{ '%.2f' | format(n) }} kWh{% endif %}"
        "{% else %}—{% endif %}"
    )


def _owner_generation_markdown_line(
    label: str,
    generation_entity_id: str,
    value_entity_id: str,
) -> str:
    """Return a markdown line with actual owner generation."""
    return (
        f"- **{label}:** "
        f"{{% set v = state_attr('{generation_entity_id}', 'raw_generation_kwh') %}}"
        "{% if v is not none %}"
        "{% set n = v | float(0) %}"
        "{% if n >= 1000000000000000 %}{{ '%.2f' | format(n / 1000000000000000) }} EWh"
        "{% elif n >= 1000000000000 %}{{ '%.2f' | format(n / 1000000000000) }} PWh"
        "{% elif n >= 1000000000 %}{{ '%.2f' | format(n / 1000000000) }} TWh"
        "{% elif n >= 1000000 %}{{ '%.2f' | format(n / 1000000) }} GWh"
        "{% elif n >= 1000 %}{{ '%.2f' | format(n / 1000) }} MWh"
        "{% else %}{{ '%.2f' | format(n) }} kWh{% endif %}"
        "{% else %}—{% endif %}"
    )


def _generation_markdown_card(title: str, entries: list[tuple[str, str]]) -> dict:
    """Return a markdown card for formatted generation display."""
    content = "\n".join(_generation_markdown_line(label, entity_id) for label, entity_id in entries)
    return {
        "type": "markdown",
        "title": title,
        "content": content,
    }


def _owner_generation_markdown_card(
    title: str,
    entries: list[tuple[str, str, str]],
) -> dict:
    """Return a markdown card for owner generation and value display."""
    content = "\n".join(
        _owner_generation_markdown_line(label, generation_entity_id, value_entity_id)
        for label, generation_entity_id, value_entity_id in entries
    )
    return {
        "type": "markdown",
        "title": title,
        "content": content,
    }


# ---------------------------------------------------------------------------
# Dashboard merge helpers — preserve user customisations across reloads
# ---------------------------------------------------------------------------

def _card_match_key(card: dict) -> str | None:
    """Return a stable key used to match a card across default updates."""
    ctype = card.get("type", "")
    # Headings are matched by heading text
    if ctype == "heading":
        return f"heading:{card.get('heading', '')}"
    # Stat / gauge / tile / entity KPI cards matched by name (entity as
    # fallback). The card type is deliberately excluded so that stored `stat`
    # cards (removed in HA 2026.7) are replaced by the new `entity` cards on
    # the next merge.
    if ctype in ("stat", "gauge", "tile", "entity"):
        key = card.get("name") or card.get("entity")
        if key:
            return f"kpi:name:{key}"
    # Entity / entities cards matched by title
    if card.get("title"):
        return f"{ctype}:title:{card['title']}"
    # Button cards matched by name
    if card.get("name") and ctype == "button":
        return f"button:name:{card['name']}"
    # Markdown cards matched by title
    if ctype == "markdown" and card.get("title"):
        return f"markdown:title:{card['title']}"
    # History-graph matched by title
    if ctype == "history-graph" and card.get("title"):
        return f"history-graph:title:{card['title']}"
    # Custom cards matched by type + title
    if ctype.startswith("custom:") and card.get("title"):
        return f"{ctype}:title:{card['title']}"
    # ApexCharts cards store title in header.title
    if ctype == "custom:apexcharts-card" and card.get("header", {}).get("title"):
        return f"{ctype}:title:{card['header']['title']}"
    return None


def _section_signature(section: dict) -> str:
    """Structural signature for sections without a heading card."""
    return "|".join(
        key
        for key in (_card_match_key(card) for card in section.get("cards", []))
        if key is not None
    )


def _section_match_key(section: dict) -> str | None:
    """Return a key used to match sections across default updates."""
    for card in section.get("cards", []):
        if card.get("type") == "heading":
            return f"heading:{card.get('heading', '')}"
    # Managed sections without a heading (e.g. the KPI row) fall back to a
    # structural signature so they can still be matched and updated.
    signature = _section_signature(section)
    return f"section:{signature}" if signature else None


def _merge_cards(existing_cards: list[dict], new_cards: list[dict]) -> list[dict]:
    """Replace managed cards and preserve user-added cards.

    Cards with a matching key are replaced by the new default version.
    Cards without a match in the new default are preserved (user-added).
    New cards without a match in existing are appended.
    """
    merged: list[dict] = []
    remaining_existing = list(existing_cards)

    for new_card in new_cards:
        new_key = _card_match_key(new_card)
        if new_key is None:
            # Can't match — treat as new, add it
            merged.append(copy.deepcopy(new_card))
            continue

        # Replace the matching existing card(s). Replace all matches so any
        # duplicates left behind by earlier versions are cleaned up too.
        remaining_existing = [
            existing_card
            for existing_card in remaining_existing
            if _card_match_key(existing_card) != new_key
        ]
        merged.append(copy.deepcopy(new_card))

    # Any remaining existing cards are user-added — preserve them at the end
    merged.extend(copy.deepcopy(remaining_existing))
    return merged


def _merge_section(existing_section: dict, new_section: dict) -> dict:
    """Merge a section, replacing managed cards and preserving user cards."""
    merged = copy.deepcopy(existing_section)
    existing_cards = merged.get("cards", [])
    new_cards = new_section.get("cards", [])
    merged["cards"] = _merge_cards(existing_cards, new_cards)
    return merged


def _merge_view(existing_view: dict, new_view: dict) -> dict:
    """Merge a view, preserving user-added sections and cards."""
    merged = copy.deepcopy(existing_view)

    # Update view-level properties from default
    for key in ("title", "icon", "type", "max_columns"):
        if key in new_view:
            merged[key] = new_view[key]

    # Sections-type views
    if new_view.get("type") == "sections" and "sections" in new_view:
        existing_sections = merged.get("sections", [])
        new_sections = new_view["sections"]
        merged_sections: list[dict] = []
        remaining_existing = list(existing_sections)

        for new_section in new_sections:
            new_key = _section_match_key(new_section)
            if new_key is None:
                merged_sections.append(copy.deepcopy(new_section))
                continue

            # Merge into the first matching existing section and drop any
            # further duplicates (e.g. KPI rows duplicated by older versions).
            match = next(
                (
                    existing_section
                    for existing_section in remaining_existing
                    if _section_match_key(existing_section) == new_key
                ),
                None,
            )
            remaining_existing = [
                existing_section
                for existing_section in remaining_existing
                if _section_match_key(existing_section) != new_key
            ]
            if match is not None:
                merged_sections.append(_merge_section(match, new_section))
            else:
                merged_sections.append(copy.deepcopy(new_section))

        # Preserve user-added sections at the end
        merged_sections.extend(remaining_existing)
        merged["sections"] = merged_sections

    # Direct-cards views (e.g. Turbines)
    elif "cards" in new_view:
        existing_cards = merged.get("cards", [])
        new_cards = new_view["cards"]
        merged["cards"] = _merge_cards(existing_cards, new_cards)

    return merged


def _merge_dashboard_config(existing: dict, new_default: dict) -> dict:
    """Merge new default dashboard with existing user customisations.

    Views and sections matched by path/heading are updated with new defaults.
    User-added views, sections, and cards are preserved.
    """
    if not existing or "views" not in existing:
        return copy.deepcopy(new_default)

    merged = copy.deepcopy(new_default)
    existing_views = existing["views"]
    new_views = merged.get("views", [])
    merged_views: list[dict] = []
    remaining_existing_views = list(existing_views)

    for new_view in new_views:
        new_path = new_view.get("path")
        found = False
        for i, existing_view in enumerate(remaining_existing_views):
            if existing_view.get("path") == new_path:
                merged_views.append(_merge_view(existing_view, new_view))
                remaining_existing_views.pop(i)
                found = True
                break

        if not found:
            merged_views.append(copy.deepcopy(new_view))

    # Preserve user-added views
    merged_views.extend(remaining_existing_views)
    merged["views"] = merged_views
    return merged


def _build_dashboard_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Generate the default storage dashboard config."""
    entity_ids = _entity_ids_for_entry(hass, entry)

    def farm_scoped(scope: str, suffix: str) -> str:
        return entity_ids[f"{entry.entry_id}_{scope}_{suffix}"]

    def farm(unique_suffix: str) -> str:
        return entity_ids[f"{entry.entry_id}_{unique_suffix}"]

    def turbine(turbine_id: str, unique_suffix: str) -> str:
        return entity_ids[f"{entry.entry_id}_turbine_{turbine_id}_{unique_suffix}"]

    owner_generation_entities = [
        (
            "Yesterday",
            farm_scoped("owner", "farm_generation_yesterday"),
            farm_scoped("owner", "farm_generation_value_yesterday"),
        ),
        (
            "Today",
            farm_scoped("owner", "farm_generation_today"),
            farm_scoped("owner", "farm_generation_value_today"),
        ),
        (
            "Week",
            farm_scoped("owner", "farm_generation_week"),
            farm_scoped("owner", "farm_generation_value_week"),
        ),
        (
            "Month",
            farm_scoped("owner", "farm_generation_month"),
            farm_scoped("owner", "farm_generation_value_month"),
        ),
        (
            "YTD",
            farm_scoped("owner", "farm_generation_ytd"),
            farm_scoped("owner", "farm_generation_value_ytd"),
        ),
        (
            "Year",
            farm_scoped("owner", "farm_generation_year"),
            farm_scoped("owner", "farm_generation_value_year"),
        ),
        (
            "All time",
            farm_scoped("owner", "farm_generation_alltime"),
            farm_scoped("owner", "farm_generation_value_alltime"),
        ),
    ]
    owner_value_entities = [
        {"entity": farm_scoped("owner", "farm_generation_value_yesterday"), "name": "Yesterday"},
        {"entity": farm_scoped("owner", "farm_generation_value_today"), "name": "Today"},
        {"entity": farm_scoped("owner", "farm_generation_value_week"), "name": "Week"},
        {"entity": farm_scoped("owner", "farm_generation_value_month"), "name": "Month"},
        {"entity": farm_scoped("owner", "farm_generation_value_ytd"), "name": "YTD"},
        {"entity": farm_scoped("owner", "farm_generation_value_year"), "name": "Year"},
        {"entity": farm_scoped("owner", "farm_generation_value_alltime"), "name": "All time"},
    ]
    site_value_entities = [
        {"entity": farm_scoped("site", "farm_generation_value_yesterday"), "name": "Yesterday"},
        {"entity": farm_scoped("site", "farm_generation_value_today"), "name": "Today"},
        {"entity": farm_scoped("site", "farm_generation_value_week"), "name": "Week"},
        {"entity": farm_scoped("site", "farm_generation_value_month"), "name": "Month"},
        {"entity": farm_scoped("site", "farm_generation_value_ytd"), "name": "YTD"},
        {"entity": farm_scoped("site", "farm_generation_value_year"), "name": "Year"},
        {"entity": farm_scoped("site", "farm_generation_value_alltime"), "name": "All time"},
    ]
    site_generation_entities = [
        ("Yesterday", farm_scoped("site", "farm_generation_yesterday")),
        ("Today", farm_scoped("site", "farm_generation_today")),
        ("Week", farm_scoped("site", "farm_generation_week")),
        ("Month", farm_scoped("site", "farm_generation_month")),
        ("YTD", farm_scoped("site", "farm_generation_ytd")),
        ("Year", farm_scoped("site", "farm_generation_year")),
        ("All time", farm_scoped("site", "farm_generation_alltime")),
    ]
    forecast_entities = [
        {
            "entity": farm("open_meteo_next_hour_wind_speed_mps"),
            "name": "Forecast next hour (Open-Meteo)",
        },
        {
            "entity": farm("open_meteo_next_3h_avg_wind_speed_mps"),
            "name": "Forecast next 3h avg (Open-Meteo)",
        },
        {
            "entity": farm("open_meteo_next_24h_avg_wind_speed_mps"),
            "name": "Forecast next 24h avg (Open-Meteo)",
        },
    ]
    turbine_map_entities = [
        {
            "name": f"T{i}",
            "state_entity": turbine(f"T{i}", "state_text"),
            "power_entity": turbine(f"T{i}", "site_power"),
            "capacity_entity": turbine(f"T{i}", "site_capacity_factor"),
            "active_entity": turbine(f"T{i}", "active"),
        }
        for i in range(1, 9)
    ]

    scada_turbines = [
        {
            "id": f"T{i}",
            "power_entity": turbine(f"T{i}", "site_power"),
            "state_entity": turbine(f"T{i}", "state_text"),
            "generation_today_entity": turbine(f"T{i}", "generation_today"),
            "rotor_entity": turbine(f"T{i}", "rotor_speed"),
        }
        for i in range(1, 9)
    ]

    turbine_cards = []
    for i in range(1, 9):
        turbine_id = f"T{i}"
        turbine_cards.append(
            {
                "type": "entities",
                "title": f"Turbine {turbine_id}",
                "entities": [
                    {"entity": turbine(turbine_id, "owner_power"), "name": "Owner power"},
                    {"entity": turbine(turbine_id, "site_power"), "name": "Site power"},
                    {"entity": turbine(turbine_id, "state_text"), "name": "State"},
                    {"entity": turbine(turbine_id, "active"), "name": "Active"},
                ],
            }
        )

    graph_hours = entry.options.get(CONF_GRAPH_HOURS, DEFAULT_GRAPH_HOURS)

    turbine_status_barchart = {
        "type": "history-graph",
        "title": f"Turbine Activity — last {graph_hours}h",
        "entities": [turbine(f"T{i}", "active") for i in range(1, 9)],
        "hours_to_show": graph_hours,
    }

    kpi_cards = [
        {
            "type": "entity",
            "name": "Owner Power",
            "entity": farm_scoped("owner", "farm_power"),
            "icon": "mdi:flash",
        },
        {
            "type": "entity",
            "name": "Site Power",
            "entity": farm_scoped("site", "farm_power"),
            "icon": "mdi:transmission-tower",
        },
        {
            "type": "gauge",
            "entity": farm_scoped("owner", "farm_capacity_factor"),
            "name": "Capacity Factor",
            "min": 0,
            "max": 100,
            "severity": {"green": 50, "yellow": 20, "red": 0},
        },
        {
            "type": "entity",
            "name": "Wind Speed",
            "entity": farm("farm_wind_speed"),
            "icon": "mdi:weather-windy",
        },
        {
            "type": "tile",
            "entity": farm("farm_alarm"),
            "name": "Alarm",
            "icon": "mdi:alert",
            "color": "red",
        },
        {
            "type": "button",
            "name": "Reload integration",
            "icon": "mdi:reload",
            "show_name": False,
            "show_state": False,
            "tap_action": {
                "action": "call-service",
                "service": "kirkhill_wind.reload_integration",
            },
        },
    ]

    financial_kpi_cards = [
        {
            "type": "entity",
            "name": "Today's Earnings",
            "entity": farm_scoped("owner", "farm_generation_value_today"),
            "icon": "mdi:cash",
        },
        {
            "type": "entity",
            "name": "This Month",
            "entity": farm_scoped("owner", "farm_generation_value_month"),
            "icon": "mdi:calendar-month",
        },
        {
            "type": "entity",
            "name": "Year to Date",
            "entity": farm_scoped("owner", "farm_generation_value_ytd"),
            "icon": "mdi:chart-timeline-variant",
        },
    ]

    return {
        "title": "Wind Farm",
        "views": [
            {
                "title": "SCADA",
                "path": "scada",
                "icon": "mdi:sitemap",
                "panel": True,
                "cards": [
                    {
                        "type": "custom:kirkhill-wind-scada",
                        "title": "Wind farm SCADA",
                        "farm_power_entity": farm_scoped("site", "farm_power"),
                        "grid_energy_entity": farm_scoped("site", "farm_generation_today"),
                        "wind_speed_entity": farm("farm_wind_speed"),
                        "active_entity": farm("farm_active_turbines"),
                        "turbines": scada_turbines,
                    },
                ],
            },
            {
                "title": "Overview",
                "path": "overview",
                "icon": "mdi:wind-turbine",
                "type": "sections",
                "max_columns": 2,
                "sections": [
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": kpi_cards,
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Your share",
                                "heading_style": "title",
                            },
                            _owner_generation_markdown_card(
                                "Owner generation",
                                owner_generation_entities,
                            ),
                            {
                                "type": "entities",
                                "title": "Owner projected earnings",
                                "show_header_toggle": False,
                                "entities": owner_value_entities,
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Whole site",
                                "heading_style": "title",
                            },
                            _generation_markdown_card(
                                "Site generation",
                                site_generation_entities,
                            ),
                            {
                                "type": "entities",
                                "title": "Site metrics",
                                "show_header_toggle": False,
                                "entities": [
                                    {
                                        "entity": farm_scoped("site", "farm_power"),
                                        "name": "Site power",
                                    },
                                    {
                                        "entity": farm_scoped("site", "farm_capacity_factor"),
                                        "name": "Site capacity factor",
                                    },
                                    {
                                        "entity": farm("farm_wind_speed"),
                                        "name": "Actual wind speed (Kirk Hill API)",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Charts",
                                "heading_style": "title",
                                "icon": "mdi:chart-line",
                            },
                            {
                                "type": "history-graph",
                                "title": "Power and Wind (last 25 hours)",
                                "hours_to_show": 25,
                                "entities": [
                                    farm_scoped("owner", "farm_power"),
                                    farm_scoped("site", "farm_power"),
                                    farm("farm_wind_speed"),
                                ],
                            },
                            {
                                "type": "custom:apexcharts-card",
                                "graph_span": "25h",
                                "apex_config": {
                                    "legend": {"show": False},
                                    "stroke": {"width": 2},
                                },
                                "header": {
                                    "show": True,
                                    "title": "Power — Owner (blue) / Site (orange)",
                                    "show_states": True,
                                    "colorize_states": True,
                                },
                                "series": [
                                    {
                                        "entity": farm_scoped("owner", "farm_power"),
                                        "fill_raw": "last",
                                        "color": "blue",
                                        "unit": "kW",
                                        "type": "area",
                                    },
                                    {
                                        "entity": farm_scoped("site", "farm_power"),
                                        "fill_raw": "last",
                                        "color": "orange",
                                        "unit": "kW",
                                        "transform": "return x * 1000;",
                                        "type": "area",
                                    },
                                ],
                            },
                            {
                                "type": "custom:plotly-graph",
                                "hours_to_show": 25,
                                "refresh_interval": "auto",
                                "entities": [
                                    {
                                        "entity": farm_scoped("owner", "farm_power"),
                                        "y_axis": "y",
                                        "line": {"width": 2},
                                    },
                                    {
                                        "entity": farm_scoped("site", "farm_power"),
                                        "y_axis": "y2",
                                        "line": {"width": 2},
                                    },
                                    {
                                        "entity": farm("farm_wind_speed"),
                                        "y_axis": "y3",
                                        "line": {"width": 1, "dash": "dot"},
                                    },
                                ],
                                "layout": {
                                    "title": "Power & Wind (25h)",
                                    "yaxis": {"title": "Owner (kW)", "side": "left"},
                                    "yaxis2": {
                                        "title": "Site (kW)",
                                        "overlaying": "y",
                                        "side": "right",
                                    },
                                    "yaxis3": {
                                        "title": "Wind (m/s)",
                                        "overlaying": "y",
                                        "side": "right",
                                        "showgrid": False,
                                    },
                                },
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Wind Forecast",
                                "heading_style": "title",
                                "icon": "mdi:weather-partly-cloudy",
                            },
                            {
                                "type": "entities",
                                "title": "Open-Meteo forecasts",
                                "show_header_toggle": False,
                                "entities": forecast_entities,
                            },
                            _owner_generation_markdown_card(
                                "Today's summary",
                                [
                                    (
                                        "Generation",
                                        farm_scoped("owner", "farm_generation_today"),
                                        farm_scoped("owner", "farm_generation_value_today"),
                                    ),
                                ],
                            ),
                        ],
                    },
                ],
            },
            {
                "title": "Finances",
                "path": "finances",
                "icon": "mdi:cash-multiple",
                "type": "sections",
                "max_columns": 2,
                "sections": [
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Finances",
                                "heading_style": "title",
                                "icon": "mdi:cash-multiple",
                            },
                            *financial_kpi_cards,
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Owner finances",
                                "heading_style": "title",
                            },
                            {
                                "type": "entities",
                                "title": "Owner projected earnings by timeframe",
                                "show_header_toggle": False,
                                "entities": owner_value_entities,
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Site finances",
                                "heading_style": "title",
                            },
                            {
                                "type": "entities",
                                "title": "Site projected value by timeframe",
                                "show_header_toggle": False,
                                "entities": site_value_entities,
                            },
                        ],
                    },
                ],
            },
            {
                "title": "Turbines",
                "path": "turbines",
                "icon": "mdi:wind-turbine",
                "cards": [
                    {
                        "type": "vertical-stack",
                        "cards": [
                            turbine_status_barchart,
                            {
                                "type": "custom:kirkhill-wind-turbine-map",
                                "title": "Turbine map",
                                "zoom": 15,
                                "turbines": turbine_map_entities,
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "columns": 2,
                        "square": False,
                        "cards": turbine_cards,
                    }
                ],
            },
        ],
    }
