"""The Kirk Hill Wind Farm integration."""
from __future__ import annotations

import copy
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.frontend import (
    add_extra_js_url,
    remove_extra_js_url,
)
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
    CONF_BASE_URL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_GRAPH_HOURS,
    CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_BASE_URL,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_GRAPH_HOURS,
    DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    PLATFORMS,
    SCOPE_OWNER,
    SCOPE_SITE,
)
from .coordinator import KirkHillWindCoordinator
from .device import get_farm_device_id
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)
_FRONTEND_DIR = Path(__file__).parent / "frontend"
_FRONTEND_REGISTERED = "kirkhill_wind_frontend_registered"
_FRONTEND_URLS = "kirkhill_wind_frontend_urls"
_ETHEX_DOMAIN = "ethex"

_FRONTEND_CARDS: list[tuple[str, Path]] = [
    ("/kirkhill_wind/turbine-map-card.js", _FRONTEND_DIR / "kirkhill-wind-turbine-map.js"),
    ("/kirkhill_wind/apexcharts-card.js", _FRONTEND_DIR / "apexcharts-card.js"),
    ("/kirkhill_wind/plotly-graph-card.js", _FRONTEND_DIR / "plotly-graph-card.js"),
    ("/kirkhill_wind/scada-card.js", _FRONTEND_DIR / "kirkhill-wind-scada-card.js"),
]

# Lazily-loaded assets: served over the same static path but NOT injected on
# every page. The SCADA card loads these on demand (e.g. ApexCharts before
# rendering the turbine detail modal charts).
_FRONTEND_ASSETS: list[tuple[str, Path]] = [
    ("/kirkhill_wind/apexcharts.js", _FRONTEND_DIR / "apexcharts.js"),
]

# Keep in sync with the VERSION in config_flow.py. Home Assistant calls this
# module-level handler when a stored config entry's version is behind.
_CONFIG_ENTRY_VERSION = 4


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Migrate a stored config entry to the current version."""
    if config_entry.version == _CONFIG_ENTRY_VERSION:
        return True

    data = dict(config_entry.data)

    if config_entry.version < 3:
        # Version 3 introduced the base_url field so users can target a
        # non-default Kirk Hill dashboard instance.
        data.setdefault(CONF_BASE_URL, DEFAULT_BASE_URL)

    if config_entry.version < 4:
        # Version 4 removed the redundant owner_share_percent (now derived from
        # the API's capacity_watts ratio) and the unused legacy
        # owner_value_rate field.
        data.pop("owner_share_percent", None)
        data.pop("owner_value_rate", None)

    hass.config_entries.async_update_entry(
        config_entry, data=data, version=_CONFIG_ENTRY_VERSION
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kirk Hill Wind Farm from a config entry."""
    coordinator = KirkHillWindCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    coordinator.farm_device_id = await get_farm_device_id(hass, entry)

    # Seed the user-adjustable projected-earnings figures that the number
    # platform exposes. The default (config) values are only the starting point;
    # users override them live via the number entities, which write back here.
    coordinator.projected_annual_earnings_gbp = {
        SCOPE_OWNER: float(
            entry.options.get(
                CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                entry.data.get(
                    CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                    DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                ),
            )
        ),
        SCOPE_SITE: float(
            entry.options.get(
                CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                entry.data.get(
                    CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                    DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                ),
            )
        ),
    }

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
        # Remove any versioned JS URLs this integration registered so they don't
        # linger in the frontend registry after the integration is unloaded.
        for url in hass.data.pop(_FRONTEND_URLS, ()):
            remove_extra_js_url(hass, url)

    return unload_ok


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register bundled custom Lovelace cards (turbine map, ApexCharts, Plotly)."""
    if not hass.data.get(_FRONTEND_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(url, str(path), False)
                for url, path in _FRONTEND_CARDS + _FRONTEND_ASSETS
            ]
        )
        hass.data[_FRONTEND_REGISTERED] = True

    # (Re-)add the versioned URLs so the browser picks up JS changes after an
    # integration reload without needing a full HA restart. Track the URLs we
    # previously registered so stale versions can be removed — otherwise each
    # reload stacks duplicate `?v=<mtime>` URLs that HA keeps forever and the
    # browser re-downloads every historical bundle (including ~4.7 MB charts).
    registered_urls = hass.data.setdefault(_FRONTEND_URLS, set())
    new_urls: set[str] = set()

    for url, path in _FRONTEND_CARDS:
        js_version = int(path.stat().st_mtime)
        new_url = f"{url}?v={js_version}"
        new_urls.add(new_url)
        if new_url not in registered_urls:
            add_extra_js_url(hass, new_url)

    for stale in registered_urls - new_urls:
        remove_extra_js_url(hass, stale)
    registered_urls.clear()
    registered_urls.update(new_urls)


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
            if "url_already_exists" in str(err):
                # Race: another call created it. Re-fetch and continue.
                _LOGGER.debug("Dashboard URL already exists (race), fetching existing item")
                await dashboards_collection.async_load()
                item = next(
                    (
                        existing
                        for existing in dashboards_collection.async_items()
                        if existing.get(CONF_URL_PATH) == url_path
                    ),
                    None,
                )
            else:
                _LOGGER.warning("Failed to create Lovelace dashboard: %s", err)
                return
    if item is None:
        _LOGGER.warning("Dashboard item not found after creation/lookup; aborting")
        return

    lovelace_store = hass.data[LOVELACE_DATA].dashboards.get(url_path)
    if lovelace_store is None:
        lovelace_store = lovelace_dashboard.LovelaceStorage(hass, item)
        hass.data[LOVELACE_DATA].dashboards[url_path] = lovelace_store

    new_default = _build_dashboard_config(hass, entry)
    try:
        existing_config = await lovelace_store.async_load(False)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Failed to load existing dashboard config: %s; creating new default", err)
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

    if hass.config_entries.flow.async_progress_by_handler(_ETHEX_DOMAIN):
        _LOGGER.info("Payment tracking enabled: Ethex config flow already in progress")
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


# Jinja fragment that formats a kWh value (already bound to `n`) with scaled units.
_SCALED_ENERGY_JINJA = (
    "{% if n >= 1000000000000000 %}{{ '%.2f' | format(n / 1000000000000000) }} EWh"
    "{% elif n >= 1000000000000 %}{{ '%.2f' | format(n / 1000000000000) }} PWh"
    "{% elif n >= 1000000000 %}{{ '%.2f' | format(n / 1000000000) }} TWh"
    "{% elif n >= 1000000 %}{{ '%.2f' | format(n / 1000000) }} GWh"
    "{% elif n >= 1000 %}{{ '%.2f' | format(n / 1000) }} MWh"
    "{% else %}{{ '%.2f' | format(n) }} kWh{% endif %}"
)


def _generation_markdown_line(label: str, entity_id: str) -> str:
    """Return a markdown line that formats generation with scaled energy units."""
    return (
        f"- **{label}:** "
        f"{{% set v = state_attr('{entity_id}', 'raw_generation_kwh') %}}"
        "{% if v is not none %}"
        "{% set n = v | float(0) %}"
        + _SCALED_ENERGY_JINJA
        + "{% else %}—{% endif %}"
    )


def _owner_generation_markdown_line(
    label: str,
    generation_entity_id: str,
    value_entity_id: str,
) -> str:
    """Return a markdown line with actual owner generation and its value."""
    return (
        f"- **{label}:** "
        f"{{% set v = state_attr('{generation_entity_id}', 'raw_generation_kwh') %}}"
        "{% if v is not none %}"
        "{% set n = v | float(0) %}"
        + _SCALED_ENERGY_JINJA
        + "{% else %}—{% endif %}"
        " ("
        f"{{% set w = states('{value_entity_id}') %}}"
        "{% if w not in ['unknown', 'unavailable', 'none', ''] %}"
        "£{{ '%.2f' | format(w | float(0)) }}"
        "{% else %}—{% endif %}"
        ")"
    )


def _generation_markdown_card(title: str, entries: list[tuple[str, str | None]]) -> dict:
    """Return a markdown card for formatted generation display.

    Entries whose entity id is missing (None) are skipped so the card degrades
    gracefully instead of referencing a non-existent entity.
    """
    lines = [
        _generation_markdown_line(label, entity_id)
        for label, entity_id in entries
        if entity_id is not None
    ]
    return {
        "type": "markdown",
        "title": title,
        "content": "\n".join(lines),
    }


def _owner_generation_markdown_card(
    title: str,
    entries: list[tuple[str, str | None, str | None]],
) -> dict:
    """Return a markdown card for owner generation and value display.

    Entries whose entity ids are missing (None) are skipped.
    """
    lines = [
        _owner_generation_markdown_line(label, generation_entity_id, value_entity_id)
        for label, generation_entity_id, value_entity_id in entries
        if generation_entity_id is not None and value_entity_id is not None
    ]
    return {
        "type": "markdown",
        "title": title,
        "content": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Dashboard merge helpers — preserve user customisations across reloads
# ---------------------------------------------------------------------------

# Cards/sections removed from the managed default. The merge otherwise treats
# any existing card or section without a default match as "user-added" and
# preserves it forever, so removed defaults must be listed here to actually
# disappear from installed dashboards on the next reload.
_OBSOLETE_CARD_KEYS: set[str] = {
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
}
# Obsolete view paths — views with these paths are removed from existing dashboards on merge.
_OBSOLETE_VIEW_PATHS: set[str] = {
    "overview",
}
_OBSOLETE_SECTION_KEYS: dict[str, set[str]] = {
    "overview": {
        "heading:Wind Forecast",
        "heading:Charts",
        # KPI row (unheaded grid) from v4.8.12 and earlier
        "section:kpi:name:Capacity Factor|kpi:name:Alarm|button:name:Reload integration",
        "section:kpi:name:Owner Power|kpi:name:Site Power|kpi:name:Capacity Factor|kpi:name:Wind Speed|"
        "kpi:name:Alarm|button:name:Reload integration",
    },
}

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
    # Container cards without a title (vertical-stack / horizontal-stack /
    # grid) get a structural key derived from the ordered match keys of their
    # child cards. Without this they are unmatchable, so _merge_cards appends
    # a fresh copy on every reload while preserving the old one, duplicating
    # them (seen on the Turbines view).
    if ctype in ("vertical-stack", "horizontal-stack", "grid"):
        child_keys = [
            key
            for key in (_card_match_key(child) for child in card.get("cards", []))
            if key is not None
        ]
        if child_keys:
            return f"container:{ctype}:{'|'.join(child_keys)}"
    # The SCADA card is a single managed card in the panel view; its title is
    # intentionally empty, so match purely by type. This ensures corrected
    # defaults replace the stored copy (and avoids duplicate SCADA cards on
    # reload) rather than being preserved as a separate "user-added" card.
    if ctype == "custom:kirkhill-wind-scada":
        return ctype
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


def _section_card_keys(section: dict) -> set[str]:
    """Set of managed-card match keys contained in a section."""
    return {
        key
        for key in (_card_match_key(card) for card in section.get("cards", []))
        if key is not None
    }


def _sections_match(existing_section: dict, new_section: dict) -> bool:
    """Match a stored section to a managed default section.

    Headed sections match on heading text. Unheaded sections (e.g. the KPI
    row) match when their card-key sets overlap with one as a subset of the
    other, so cards removed from (or added to) a default don't orphan the old
    section as "user-added" and leave stale cards behind.
    """
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

    # Any remaining existing cards are either user-added or obsolete defaults
    # that were removed from the managed dashboard — drop the latter.
    merged.extend(
        copy.deepcopy(existing_card)
        for existing_card in remaining_existing
        if (_card_match_key(existing_card) or "") not in _OBSOLETE_CARD_KEYS
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

        # Preserve user-added sections at the end, dropping obsolete defaults
        # that were removed from the managed dashboard for this view path.
        obsolete_sections = _OBSOLETE_SECTION_KEYS.get(new_view.get("path") or "", set())
        merged_sections.extend(
            section
            for section in remaining_existing
            if (_section_match_key(section) or "") not in obsolete_sections
        )
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

    # Preserve user-added views (but drop obsolete ones)
    merged_views.extend(
        v for v in remaining_existing_views
        if v.get("path") not in _OBSOLETE_VIEW_PATHS
    )
    merged["views"] = merged_views
    return merged


def _build_dashboard_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Generate the default storage dashboard config."""
    entity_ids = _entity_ids_for_entry(hass, entry)

    def farm_scoped(scope: str, suffix: str) -> str | None:
        return entity_ids.get(f"{entry.entry_id}_{scope}_{suffix}")

    def farm(unique_suffix: str) -> str | None:
        return entity_ids.get(f"{entry.entry_id}_{unique_suffix}")

    def turbine(turbine_id: str, unique_suffix: str) -> str | None:
        return entity_ids.get(f"{entry.entry_id}_turbine_{turbine_id}_{unique_suffix}")

    # Build the turbine list from the turbine ids that actually have entities
    # in the registry, rather than hard-coding T1-T8. Turbine entities are only
    # created for ids present in the API response, so the two can diverge and the
    # hard-coded list raised KeyError when a turbine was missing.
    turbine_prefix = f"{entry.entry_id}_turbine_"
    present_turbine_ids = sorted(
        {
            uid[len(turbine_prefix):].split("_")[0]
            for uid in entity_ids
            if uid.startswith(turbine_prefix)
        }
    )
    if not present_turbine_ids:
        # No turbine entities registered yet (e.g. first poll hasn't completed).
        # Fall back to T1-T8 so the SCADA card config doesn't throw.
        _LOGGER.debug("No turbine entities registered yet; falling back to T1–T8")
        present_turbine_ids = [f"T{i}" for i in range(1, 9)]

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
    site_generation_entities = [
        ("Yesterday", farm_scoped("site", "farm_generation_yesterday")),
        ("Today", farm_scoped("site", "farm_generation_today")),
        ("Week", farm_scoped("site", "farm_generation_week")),
        ("Month", farm_scoped("site", "farm_generation_month")),
        ("YTD", farm_scoped("site", "farm_generation_ytd")),
        ("Year", farm_scoped("site", "farm_generation_year")),
        ("All time", farm_scoped("site", "farm_generation_alltime")),
    ]
    turbine_map_entities = [
        {
            "name": tid,
            "state_entity": turbine(tid, "state_text"),
            "power_entity": turbine(tid, "site_power"),
            "capacity_entity": turbine(tid, "site_capacity_factor"),
            "active_entity": turbine(tid, "active"),
        }
        for tid in present_turbine_ids
    ]

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

    turbine_cards = []
    for tid in present_turbine_ids:
        turbine_cards.append(
            {
                "type": "entities",
                "title": f"Turbine {tid}",
                "entities": [
                    {"entity": turbine(tid, "owner_power"), "name": "Owner power"},
                    {"entity": turbine(tid, "site_power"), "name": "Site power"},
                    {"entity": turbine(tid, "state_text"), "name": "State"},
                    {"entity": turbine(tid, "active"), "name": "Active"},
                ],
            }
        )

    graph_hours = entry.options.get(CONF_GRAPH_HOURS, DEFAULT_GRAPH_HOURS)

    turbine_status_barchart = {
        "type": "history-graph",
        "title": f"Turbine Activity — last {graph_hours}h",
        "entities": [
            tid_entity
            for tid_entity in (turbine(tid, "active") for tid in present_turbine_ids)
            if tid_entity is not None
        ],
        "hours_to_show": graph_hours,
    }

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
                        "title": "",
                        "farm_power_entity": farm_scoped("site", "farm_power"),
                        "grid_energy_entity": farm_scoped("site", "farm_generation_today"),
                        "owner_power_entity": farm_scoped("owner", "farm_power"),
                        "owner_grid_energy_entity": farm_scoped("owner", "farm_generation_today"),
                        "owner_generation_today_entity": farm_scoped("owner", "farm_generation_today"),
                        "owner_share_entity": farm_scoped("owner", "farm_owner_share"),
                        "wind_speed_entity": farm("farm_wind_speed"),
                        "wind_forecast_entity": farm("open_meteo_next_hour_wind_speed_mps"),
                        "active_entity": farm("farm_active_turbines"),
                        "capacity_entity": farm_scoped("site", "farm_capacity_factor"),
                        "owner_generation_entities": [
                            {"name": name, "entity": entity}
                            for name, entity, _ in owner_generation_entities
                        ],
                        "site_generation_entities": [
                            {"name": name, "entity": entity}
                            for name, entity in site_generation_entities
                        ],
                        "turbines": scada_turbines,
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
                            _owner_generation_markdown_card(
                                "Owner Generation & Projected Earnings",
                                owner_generation_entities,
                            ),
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
                            _generation_markdown_card(
                                "Site Generation",
                                site_generation_entities,
                            ),
                        ],
                    },
                ],
            },
            {
                "title": "History",
                "path": "history",
                "icon": "mdi:chart-line",
                "type": "sections",
                "max_columns": 2,
                "sections": [
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
                                    },
                                },
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
