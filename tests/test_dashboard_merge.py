"""Tests for the dashboard merge logic — the most fragile part of the integration."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.lovelace.const import LOVELACE_DATA

from custom_components.kirkhill_wind.dashboard import (
    _URL_PATH,
    OBSOLETE_CARD_KEYS,
    OBSOLETE_VIEW_PATHS,
    _merge_cards,
    async_ensure_dashboard,
    card_match_key,
    merge_dashboard_config,
)

# ---------------------------------------------------------------------------
# card_match_key
# ---------------------------------------------------------------------------


class TestCardMatchKey:
    """Verify cards are matched by stable keys."""

    def test_heading_matched_by_text(self):
        assert card_match_key({"type": "heading", "heading": "My Heading"}) == "heading:My Heading"

    def test_kpi_matched_by_name(self):
        card = {"type": "stat", "name": "Owner Power", "entity": "sensor.x"}
        assert card_match_key(card) == "kpi:name:Owner Power"

    def test_kpi_falls_back_to_entity(self):
        card = {"type": "entity", "entity": "sensor.x"}
        assert card_match_key(card) == "kpi:name:sensor.x"

    def test_entities_matched_by_title(self):
        card = {"type": "entities", "title": "Owner data"}
        assert card_match_key(card) == "entities:title:Owner data"

    def test_button_matched_by_name(self):
        card = {"type": "button", "name": "Reload integration"}
        assert card_match_key(card) == "button:name:Reload integration"

    def test_scada_card_matched_by_type(self):
        card = {"type": "custom:kirkhill-wind-scada", "title": ""}
        assert card_match_key(card) == "custom:kirkhill-wind-scada"

    def test_apexcharts_matched_by_header_title(self):
        card = {"type": "custom:apexcharts-card", "header": {"title": "Wind"}}
        assert card_match_key(card) == "custom:apexcharts-card:title:Wind"

    def test_unmatchable_card_returns_none(self):
        card = {"type": "custom:unknown"}
        assert card_match_key(card) is None

    def test_container_matched_by_child_keys(self):
        card = {
            "type": "vertical-stack",
            "cards": [
                {"type": "heading", "heading": "Test"},
                {"type": "entities", "title": "Data"},
            ],
        }
        key = card_match_key(card)
        assert key is not None
        assert "container:vertical-stack:" in key

    def test_card_type_not_included_in_kpi_key(self):
        """stat and entity cards with the same name should match."""
        stat = {"type": "stat", "name": "Power"}
        entity = {"type": "entity", "name": "Power"}
        assert card_match_key(stat) == card_match_key(entity)


# ---------------------------------------------------------------------------
# _merge_cards
# ---------------------------------------------------------------------------


class TestMergeCards:
    """Verify card merge logic preserves user cards and updates managed cards."""

    def test_managed_card_replaced(self):
        """A managed card with a matching key should be replaced by the new version."""
        existing = [
            {"type": "entities", "title": "Owner data", "old_field": True},
        ]
        new = [
            {"type": "entities", "title": "Owner data", "new_field": True},
        ]
        result = _merge_cards(existing, new)
        assert len(result) == 1
        assert result[0]["new_field"] is True
        assert "old_field" not in result[0]

    def test_user_card_preserved(self):
        """A user-added card (no match in defaults) should be preserved."""
        existing = [
            {"type": "entities", "title": "Owner data"},  # managed
            {"type": "markdown", "content": "My notes"},  # user-added (no title)
        ]
        new = [
            {"type": "entities", "title": "Owner data"},
        ]
        result = _merge_cards(existing, new)
        assert len(result) == 2
        contents = [c.get("content") or c.get("title") for c in result]
        assert "My notes" in contents

    def test_new_default_card_appended(self):
        """A new default card not in existing should be appended."""
        existing = [
            {"type": "entities", "title": "Owner data"},
        ]
        new = [
            {"type": "entities", "title": "Owner data"},
            {"type": "entities", "title": "Site data"},
        ]
        result = _merge_cards(existing, new)
        titles = [c.get("title") for c in result]
        assert "Site data" in titles

    def test_obsolete_card_removed(self):
        """Cards whose key is in OBSOLETE_CARD_KEYS should be removed."""
        # Use a known simple key to avoid set iteration non-determinism.
        obsolete_key = "entities:title:Turbine T1"
        assert obsolete_key in OBSOLETE_CARD_KEYS
        existing = [{"type": "entities", "title": "Turbine T1"}]

        new = []  # No new cards
        result = _merge_cards(existing, new)
        assert len(result) == 0

    def test_no_duplicates_after_merge(self):
        """Merge should not produce duplicate cards."""
        existing = [
            {"type": "entities", "title": "Owner data"},
        ]
        new = [
            {"type": "entities", "title": "Owner data"},
        ]
        result = _merge_cards(existing, new)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# merge_dashboard_config
# ---------------------------------------------------------------------------


class TestMergeDashboardConfig:
    """Verify full dashboard merge preserves structure."""

    def test_views_matched_by_path(self):
        existing = {
            "views": [
                {
                    "path": "scada",
                    "title": "Old Title",
                    "cards": [
                        {"type": "entities", "title": "Owner data", "version": 1},
                    ],
                },
            ],
        }
        new = {
            "views": [
                {
                    "path": "scada",
                    "title": "New Title",
                    "cards": [
                        {"type": "entities", "title": "Owner data", "version": 2},
                    ],
                },
            ],
        }
        result = merge_dashboard_config(existing, new)
        assert len(result["views"]) == 1
        assert result["views"][0]["title"] == "New Title"
        cards = result["views"][0]["cards"]
        assert cards[0]["version"] == 2

    def test_user_view_preserved(self):
        existing = {
            "views": [
                {"path": "scada", "cards": []},
                {"path": "my-custom-view", "title": "Custom", "cards": []},
            ],
        }
        new = {
            "views": [
                {"path": "scada", "cards": []},
            ],
        }
        result = merge_dashboard_config(existing, new)
        paths = [v["path"] for v in result["views"]]
        assert "my-custom-view" in paths

    def test_obsolete_view_removed(self):
        obsolete_path = next(iter(OBSOLETE_VIEW_PATHS))
        existing = {
            "views": [
                {"path": obsolete_path, "cards": []},
            ],
        }
        new = {
            "views": [],
        }
        result = merge_dashboard_config(existing, new)
        paths = [v.get("path") for v in result["views"]]
        assert obsolete_path not in paths

    def test_empty_existing_returns_default(self):
        new = {"views": [{"path": "scada", "cards": []}]}
        result = merge_dashboard_config({}, new)
        assert result["views"][0]["path"] == "scada"


# ---------------------------------------------------------------------------
# async_ensure_dashboard
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "title": "Wind Farm",
    "views": [
        {
            "title": "Kirk Hill SCADA",
            "path": "scada",
            "cards": [{"type": "heading", "heading": "Wind Farm"}],
        }
    ],
}


class _Store:
    """Stand-in for LovelaceStorage that remembers what it was asked to save."""

    def __init__(self, config=None):
        self.config = config
        self.saves: list[dict] = []

    async def async_load(self, _allow_yaml_collection):
        return self.config

    async def async_save(self, config):
        self.config = config
        self.saves.append(config)


class TestEnsureDashboardDoesNotRewriteAnUnchangedDashboard:
    """async_ensure_dashboard used to save on every config-entry update.

    The update listener runs it for *any* entry write -- including each
    number-entity price change -- so .storage/lovelace was rewritten and
    lovelace_updated fired every time: a dashboard left open reloaded, and an
    edit in progress was merged over.
    """

    async def _ensure(self, store: _Store, config: dict):
        item = {
            "url_path": _URL_PATH,
            "title": "Kirk Hill Wind Farm",
            "icon": "mdi:wind-turbine",
            "show_in_sidebar": True,
            "require_admin": False,
        }
        collection = MagicMock()
        collection.async_load = AsyncMock()
        collection.async_items = MagicMock(return_value=[item])

        entry = MagicMock()
        entry.options = {}

        hass = MagicMock()
        hass.data = {LOVELACE_DATA: SimpleNamespace(dashboards={_URL_PATH: store})}

        with (
            patch(
                "custom_components.kirkhill_wind.dashboard.lovelace_dashboard.DashboardsCollection",
                return_value=collection,
            ),
            patch(
                "custom_components.kirkhill_wind.dashboard.build_dashboard_config",
                return_value=config,
            ),
            patch("custom_components.kirkhill_wind.dashboard.frontend.async_register_built_in_panel"),
        ):
            await async_ensure_dashboard(hass, entry)
        return hass

    @pytest.mark.asyncio
    async def test_saves_the_default_once_then_leaves_it_alone(self):
        store = _Store()
        config = copy.deepcopy(_DEFAULT_CONFIG)

        await self._ensure(store, config)
        await self._ensure(store, config)

        assert len(store.saves) == 1, "the second run must find its own output current"

    @pytest.mark.asyncio
    async def test_does_not_touch_a_dashboard_that_already_matches(self):
        store = _Store(copy.deepcopy(_DEFAULT_CONFIG))

        hass = await self._ensure(store, copy.deepcopy(_DEFAULT_CONFIG))

        assert store.saves == [], "an unchanged dashboard must not be rewritten"
        hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_saves_when_the_stored_dashboard_has_drifted(self):
        store = _Store(copy.deepcopy(_DEFAULT_CONFIG))
        await self._ensure(store, copy.deepcopy(_DEFAULT_CONFIG))
        assert store.saves == [], "precondition: it starts out current"

        drifted = copy.deepcopy(_DEFAULT_CONFIG)
        drifted["title"] = "Renamed outside the integration"
        store.config = drifted

        await self._ensure(store, copy.deepcopy(_DEFAULT_CONFIG))

        assert len(store.saves) == 1, "a dashboard that drifted must still be saved"
