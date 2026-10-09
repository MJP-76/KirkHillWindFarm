"""Dashboard management for the Kirk Hill Wind Farm integration.

Handles creation, merging, and resetting of the Lovelace dashboard.
Separated from __init__.py to keep the entry-point file manageable.
"""
from __future__ import annotations

import copy
import logging

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.lovelace import dashboard as lovelace_dashboard

# Imported from lovelace.const rather than lovelace itself: these live in
# const, and lovelace only re-exports some of them, so the top-level import
# is not a stable contract across HA releases.
from homeassistant.components.lovelace.const import (
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    LOVELACE_DATA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ICON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .settings import dashboard_enabled

_LOGGER = logging.getLogger(__name__)

_URL_PATH = "kirk-hill-wind-dashboard"
_TITLE = "Kirk Hill Wind Farm"
_ICON = "mdi:wind-turbine"


# ---------------------------------------------------------------------------
# Public API — called from __init__.py
# ---------------------------------------------------------------------------


async def async_ensure_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create and register a Lovelace dashboard tab for this integration."""
    if LOVELACE_DATA not in hass.data:
        _LOGGER.debug("Lovelace not loaded yet; skipping dashboard auto-create")
        return

    if not dashboard_enabled(entry):
        _LOGGER.debug("Dashboard creation disabled for config entry %s", entry.entry_id)
        return

    dashboards_collection = lovelace_dashboard.DashboardsCollection(hass)
    await dashboards_collection.async_load()

    item = next(
        (
            existing
            for existing in dashboards_collection.async_items()
            if existing.get(CONF_URL_PATH) == _URL_PATH
        ),
        None,
    )
    if item is None:
        try:
            item = await dashboards_collection.async_create_item(
                {
                    CONF_ICON: _ICON,
                    CONF_TITLE: _TITLE,
                    CONF_URL_PATH: _URL_PATH,
                    CONF_SHOW_IN_SIDEBAR: True,
                    CONF_REQUIRE_ADMIN: False,
                }
            )
        except (HomeAssistantError, vol.Invalid) as err:
            if getattr(err, "translation_key", None) == "url_already_exists":
                _LOGGER.debug("Dashboard URL already exists (race), fetching existing item")
                await dashboards_collection.async_load()
                item = next(
                    (
                        existing
                        for existing in dashboards_collection.async_items()
                        if existing.get(CONF_URL_PATH) == _URL_PATH
                    ),
                    None,
                )
            else:
                _LOGGER.warning("Failed to create Lovelace dashboard: %s", err)
                return
    if item is None:
        _LOGGER.warning("Dashboard item not found after creation/lookup; aborting")
        return

    lovelace_store = hass.data[LOVELACE_DATA].dashboards.get(_URL_PATH)
    if lovelace_store is None:
        lovelace_store = lovelace_dashboard.LovelaceStorage(hass, item)
        hass.data[LOVELACE_DATA].dashboards[_URL_PATH] = lovelace_store

    new_default = build_dashboard_config(hass, entry)
    try:
        existing_config = await lovelace_store.async_load(False)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Failed to load existing dashboard config: %s; creating new default", err)
        existing_config = None

    if existing_config and "views" in existing_config:
        config_to_save = merge_dashboard_config(existing_config, new_default)
        _LOGGER.debug("Merged dashboard config with existing user customisations")
    else:
        config_to_save = new_default
        _LOGGER.debug("No existing dashboard found; saving default config")

    if existing_config == config_to_save:
        # The merge is idempotent, so this is the steady state after the first
        # write. Saving anyway would rewrite .storage/lovelace and fire
        # lovelace_updated on *every* config-entry update -- including each
        # number-entity price change -- which reloads any dashboard that is
        # open and clobbers an edit in progress. The panel registration below
        # still runs: it is cheap and has no user-visible effect.
        _LOGGER.debug("Dashboard already up to date; skipping save")
    else:
        await lovelace_store.async_save(config_to_save)
        hass.bus.async_fire(
            "lovelace_updated", {"url_path": _URL_PATH, "updated": True}
        )

    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        frontend_url_path=_URL_PATH,
        require_admin=item[CONF_REQUIRE_ADMIN],
        show_in_sidebar=item[CONF_SHOW_IN_SIDEBAR],
        sidebar_title=item[CONF_TITLE],
        sidebar_icon=item.get(CONF_ICON, _ICON),
        config={"mode": "storage"},
        update=True,
    )


async def async_reset_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reset the Lovelace dashboard to defaults, discarding user customisations."""
    lovelace_store = hass.data.get(LOVELACE_DATA, {}).dashboards.get(_URL_PATH)
    if lovelace_store is None:
        _LOGGER.warning("Dashboard store not found; cannot reset")
        return

    new_default = build_dashboard_config(hass, entry)
    await lovelace_store.async_save(new_default)
    hass.bus.async_fire("lovelace_updated", {"url_path": _URL_PATH, "updated": True})
    _LOGGER.info("Dashboard reset to defaults")


# ---------------------------------------------------------------------------
# Entity registry helper
# ---------------------------------------------------------------------------


def _entity_ids_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Return a map of entity unique_id to current entity_id."""
    registry = er.async_get(hass)
    entity_ids: dict[str, str] = {}

    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id:
            entity_ids[entity_entry.unique_id] = entity_entry.entity_id

    return entity_ids


# ---------------------------------------------------------------------------
# Dashboard merge helpers — preserve user customisations across reloads
# ---------------------------------------------------------------------------

# Cards/sections removed from the managed default. The merge otherwise treats
# any existing card or section without a default match as "user-added" and
# preserves it forever, so removed defaults must be listed here to actually
# disappear from installed dashboards on the next reload.
OBSOLETE_CARD_KEYS: set[str] = {
    "kpi:name:Owner Power",
    "kpi:name:Site Power",
    "kpi:name:Wind Speed",
    "kpi:name:Capacity Factor",
    "kpi:name:Alarm",
    "button:name:Reload integration",
    "entities:title:Owner projected earnings",
    "entities:title:Site metrics",
    "entities:title:Owner projected earnings by timeframe",
    "entities:title:Site projected value by timeframe",
    # Turbines view trimmed in v4.8.77
    "history-graph:title:Turbine Activity — last 24h",
    "entities:title:Turbine T1",
    "entities:title:Turbine T2",
    "entities:title:Turbine T3",
    "entities:title:Turbine T4",
    "entities:title:Turbine T5",
    "entities:title:Turbine T6",
    "entities:title:Turbine T7",
    "entities:title:Turbine T8",
    # Legacy container wrappers
    "container:vertical-stack:history-graph:title:Turbine Activity — last 24h|"
    "custom:kirkhill-wind-turbine-map:title:Turbine map",
    "container:grid:entities:title:Turbine T1|entities:title:Turbine T2|"
    "entities:title:Turbine T3|entities:title:Turbine T4|entities:title:Turbine T5|"
    "entities:title:Turbine T6|entities:title:Turbine T7|entities:title:Turbine T8",
}
OBSOLETE_VIEW_PATHS: set[str] = {
    "overview",
    "history",
    "finances",
    "turbines",
}
OBSOLETE_SECTION_KEYS: dict[str, set[str]] = {
    "overview": {
        "heading:Wind Forecast",
        "heading:Charts",
        "section:kpi:name:Capacity Factor|kpi:name:Alarm|button:name:Reload integration",
        "section:kpi:name:Owner Power|kpi:name:Site Power|kpi:name:Capacity Factor|kpi:name:Wind Speed|"
        "kpi:name:Alarm|button:name:Reload integration",
    },
}


def card_match_key(card: dict) -> str | None:
    """Return a stable key used to match a card across default updates."""
    ctype = card.get("type", "")
    if ctype == "heading":
        return f"heading:{card.get('heading', '')}"
    if ctype in ("stat", "gauge", "tile", "entity"):
        key = card.get("name") or card.get("entity")
        if key:
            return f"kpi:name:{key}"
    if card.get("title"):
        return f"{ctype}:title:{card['title']}"
    if card.get("name") and ctype == "button":
        return f"button:name:{card['name']}"
    if ctype == "markdown" and card.get("title"):
        return f"markdown:title:{card['title']}"
    if ctype == "history-graph" and card.get("title"):
        return f"history-graph:title:{card['title']}"
    if ctype.startswith("custom:"):
        card_title = card.get("title") or card.get("layout", {}).get("title")
        if card_title:
            return f"{ctype}:title:{card_title}"
    if ctype in ("vertical-stack", "horizontal-stack", "grid"):
        child_keys = [
            key
            for key in (card_match_key(child) for child in card.get("cards", []))
            if key is not None
        ]
        if child_keys:
            return f"container:{ctype}:{'|'.join(child_keys)}"
    if ctype == "custom:kirkhill-wind-scada":
        return ctype
    if ctype == "custom:apexcharts-card" and card.get("header", {}).get("title"):
        return f"{ctype}:title:{card['header']['title']}"
    return None


def _section_signature(section: dict) -> str:
    """Structural signature for sections without a heading card."""
    return "|".join(
        key
        for key in (card_match_key(card) for card in section.get("cards", []))
        if key is not None
    )


def _section_match_key(section: dict) -> str | None:
    """Return a key used to match sections across default updates."""
    for card in section.get("cards", []):
        if card.get("type") == "heading":
            return f"heading:{card.get('heading', '')}"
    signature = _section_signature(section)
    return f"section:{signature}" if signature else None


def _section_card_keys(section: dict) -> set[str]:
    """Set of managed-card match keys contained in a section."""
    return {
        key
        for key in (card_match_key(card) for card in section.get("cards", []))
        if key is not None
    }


def _sections_match(existing_section: dict, new_section: dict) -> bool:
    """Match a stored section to a managed default section."""
    existing_heading = _section_match_key(existing_section)
    new_heading = _section_match_key(new_section)
    if existing_heading and existing_heading.startswith("heading:"):
        return existing_heading == new_heading
    if new_heading and new_heading.startswith("heading:"):
        return False

    existing_keys = _section_card_keys(existing_section)
    new_keys = _section_card_keys(new_section)
    if not existing_keys or not new_keys:
        return False
    return (
        existing_keys == new_keys
        or existing_keys.issubset(new_keys)
        or new_keys.issubset(existing_keys)
    )


def _merge_cards(existing_cards: list[dict], new_cards: list[dict]) -> list[dict]:
    """Replace managed cards and preserve user-added cards."""
    merged: list[dict] = []
    remaining_existing = list(existing_cards)

    for new_card in new_cards:
        new_key = card_match_key(new_card)
        if new_key is None:
            merged.append(copy.deepcopy(new_card))
            continue

        remaining_existing = [
            existing_card
            for existing_card in remaining_existing
            if card_match_key(existing_card) != new_key
        ]
        merged.append(copy.deepcopy(new_card))

    merged.extend(
        copy.deepcopy(existing_card)
        for existing_card in remaining_existing
        if (card_match_key(existing_card) or "") not in OBSOLETE_CARD_KEYS
    )
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

    for key in ("title", "icon", "type", "max_columns"):
        if key in new_view:
            merged[key] = new_view[key]

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

            match = next(
                (
                    existing_section
                    for existing_section in remaining_existing
                    if _sections_match(existing_section, new_section)
                ),
                None,
            )
            remaining_existing = [
                existing_section
                for existing_section in remaining_existing
                if not _sections_match(existing_section, new_section)
            ]
            if match is not None:
                merged_sections.append(_merge_section(match, new_section))
            else:
                merged_sections.append(copy.deepcopy(new_section))

        obsolete_sections = OBSOLETE_SECTION_KEYS.get(new_view.get("path") or "", set())
        merged_sections.extend(
            section
            for section in remaining_existing
            if (_section_match_key(section) or "") not in obsolete_sections
        )
        merged["sections"] = merged_sections

    elif "cards" in new_view:
        existing_cards = merged.get("cards", [])
        new_cards = new_view["cards"]
        merged["cards"] = _merge_cards(existing_cards, new_cards)

    return merged


def merge_dashboard_config(existing: dict, new_default: dict) -> dict:
    """Merge new default dashboard with existing user customisations."""
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

    merged_views.extend(
        v for v in remaining_existing_views
        if v.get("path") not in OBSOLETE_VIEW_PATHS
    )
    merged["views"] = merged_views
    return merged


def build_dashboard_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Generate the default storage dashboard config."""
    entity_ids = _entity_ids_for_entry(hass, entry)

    def farm_scoped(scope: str, suffix: str) -> str | None:
        return entity_ids.get(f"{entry.entry_id}_{scope}_{suffix}")

    def farm(unique_suffix: str) -> str | None:
        return entity_ids.get(f"{entry.entry_id}_{unique_suffix}")

    def turbine(turbine_id: str, unique_suffix: str) -> str | None:
        return entity_ids.get(f"{entry.entry_id}_turbine_{turbine_id}_{unique_suffix}")

    turbine_prefix = f"{entry.entry_id}_turbine_"
    present_turbine_ids = sorted(
        {
            uid[len(turbine_prefix):].split("_")[0]
            for uid in entity_ids
            if uid.startswith(turbine_prefix)
        }
    )
    if not present_turbine_ids:
        _LOGGER.debug("No turbine entities registered yet; falling back to T1–T8")
        present_turbine_ids = [f"T{i}" for i in range(1, 9)]

    # Label and unique-id suffix for each generation timeframe, in display order.
    generation_periods = (
        ("Yesterday", "yesterday"),
        ("Today", "today"),
        ("Week", "week"),
        ("Month", "month"),
        ("YTD", "ytd"),
        ("Year", "year"),
        ("All time", "alltime"),
    )

    def generation_entities(scope: str) -> list[tuple[str, str | None, str | None]]:
        """Return (label, energy entity, value entity) triples for a generation scope."""
        return [
            (
                label,
                farm_scoped(scope, f"farm_generation_{suffix}"),
                farm_scoped(scope, f"farm_generation_value_{suffix}"),
            )
            for label, suffix in generation_periods
        ]

    owner_generation_entities = generation_entities("owner")
    site_generation_entities = generation_entities("site")
    scada_turbines = [
        {
            "id": tid,
            "power_entity": turbine(tid, "site_power"),
            "state_entity": turbine(tid, "state_text"),
            "generation_today_entity": turbine(tid, "generation_today"),
            "rotor_entity": turbine(tid, "rotor_speed"),
            "wind_speed_entity": turbine(tid, "wind_speed"),
            "capacity_entity": turbine(tid, "site_capacity_factor"),
        }
        for tid in present_turbine_ids
    ]

    return {
        "title": "Wind Farm",
        "views": [
            {
                "title": "Kirk Hill SCADA",
                "path": "scada",
                "icon": "mdi:sitemap",
                "panel": True,
                "cards": [
                    {
                        "type": "custom:kirkhill-wind-scada",
                        "title": "",
                        "farm_power_entity": farm_scoped("site", "farm_power"),
                        "grid_energy_entity": farm_scoped("site", "farm_generation_today"),
                        "owner_power_entity": farm_scoped("owner", "farm_power"),
                        "owner_grid_energy_entity": farm_scoped("owner", "farm_generation_today"),
                        "owner_generation_today_entity": farm_scoped("owner", "farm_generation_today"),
                        "owner_share_entity": farm_scoped("owner", "farm_owner_share"),
                        "negotiated_price_entity": farm("negotiated_price_gbp_per_mwh"),
                        "owner_price_entity": farm("owner_price_pence_per_kwh"),
                        "member_savings_entity": farm_scoped("owner", "member_savings_value"),
                        "wind_speed_entity": farm("farm_wind_speed"),
                        "wind_forecast_entity": farm("open_meteo_next_hour_wind_speed_mps"),
                        "active_entity": farm("farm_active_turbines"),
                        "api_status_entity": farm("api_status"),
                        "capacity_entity": farm_scoped("site", "farm_capacity_factor"),
                        "owner_generation_entities": [
                            {"name": name, "entity": entity, "value_entity": value_entity}
                            for name, entity, value_entity in owner_generation_entities
                        ],
                        "site_generation_entities": [
                            {"name": name, "entity": entity, "value_entity": value_entity}
                            for name, entity, value_entity in site_generation_entities
                        ],
                        "turbines": scada_turbines,
                    },
                ],
            },
        ],
    }
