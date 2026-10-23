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


def _fake_collection(items=None):
    coll = MagicMock()
    coll.async_load = AsyncMock()
    coll.async_items = MagicMock(return_value=list(items or []))
    coll.async_create_item = AsyncMock(side_effect=lambda payload: {**payload})
    return coll


def _fake_lovelace_store(existing=None):
    store = MagicMock()
    store.async_load = AsyncMock(return_value=existing)
    store.async_save = AsyncMock()
    return store


class TestEnsureLifecycle:
    """The dashboard lifecycle the external review asked about: disabled,
    not-loaded, first run, steady state, and user customisation."""

    def _hass(self, loaded=True):
        hass = MagicMock()
        hass.data = {}
        if loaded:
            from custom_components.kirkhill_wind.dashboard import LOVELACE_DATA
            hass.data[LOVELACE_DATA] = SimpleNamespace(dashboards={})
        return hass

    def _entry(self, enabled=True):
        entry = MagicMock()
        entry.entry_id = "lifecycle-test"
        entry.options = {"create_dashboard": enabled}
        return entry

    async def test_disabled_creation_never_touches_lovelace(self):
        import custom_components.kirkhill_wind.dashboard as dash

        hass = self._hass(loaded=True)
        with patch.object(
            dash.lovelace_dashboard, "DashboardsCollection"
        ) as coll_cls:
            await dash.async_ensure_dashboard(hass, self._entry(enabled=False))
        coll_cls.assert_not_called()

    async def test_lovelace_not_loaded_skips(self):
        import custom_components.kirkhill_wind.dashboard as dash

        hass = self._hass(loaded=False)
        with patch.object(
            dash.lovelace_dashboard, "DashboardsCollection"
        ) as coll_cls:
            await dash.async_ensure_dashboard(hass, self._entry(enabled=True))
        coll_cls.assert_not_called()

    async def test_first_run_creates_saves_and_registers(self):
        from homeassistant.components.lovelace.const import (
            CONF_URL_PATH,
        )

        import custom_components.kirkhill_wind.dashboard as dash

        hass = self._hass()
        coll = _fake_collection(items=[])
        store = _fake_lovelace_store(existing=None)
        default_config = {"views": [{"title": "SCADA"}]}
        with patch.object(
            dash.lovelace_dashboard, "DashboardsCollection"
        ) as coll_cls, patch.object(
            dash.lovelace_dashboard, "LovelaceStorage", return_value=store
        ), patch.object(
            dash, "build_dashboard_config", return_value=default_config
        ), patch.object(dash, "frontend") as frontend:
            coll_cls.return_value = coll
            await dash.async_ensure_dashboard(hass, self._entry())

        # One dashboard created with our URL path, the default saved once.
        coll.async_create_item.assert_awaited_once()
        assert coll.async_create_item.call_args[0][0][CONF_URL_PATH]
        store.async_save.assert_awaited_once_with(default_config)
        frontend.async_register_built_in_panel.assert_called_once()

    async def test_second_run_is_a_no_write_steady_state(self):
        """Reinstall/reload must not rewrite .storage on every entry update."""
        from homeassistant.components.lovelace.const import (
            CONF_REQUIRE_ADMIN,
            CONF_SHOW_IN_SIDEBAR,
            CONF_TITLE,
            CONF_URL_PATH,
        )

        import custom_components.kirkhill_wind.dashboard as dash

        hass = self._hass()
        default_config = {"views": [{"title": "SCADA"}]}
        existing_item = {
            CONF_URL_PATH: dash._URL_PATH,
            CONF_TITLE: "Kirk Hill Wind Farm",
            CONF_REQUIRE_ADMIN: False,
            CONF_SHOW_IN_SIDEBAR: True,
        }
        coll = _fake_collection(items=[existing_item])
        store = _fake_lovelace_store(existing=default_config)  # already merged
        with patch.object(
            dash.lovelace_dashboard, "DashboardsCollection"
        ) as coll_cls, patch.object(
            dash.lovelace_dashboard, "LovelaceStorage", return_value=store
        ), patch.object(
            dash, "build_dashboard_config", return_value=default_config
        ), patch.object(dash, "frontend"):
            coll_cls.return_value = coll
            await dash.async_ensure_dashboard(hass, self._entry())
            await dash.async_ensure_dashboard(hass, self._entry())

        # The existing dashboard is reused (never duplicated) …
        coll.async_create_item.assert_not_called()
        # … and the merge being idempotent means not one rewrite happened.
        store.async_save.assert_not_called()

    async def test_user_customisations_survive_the_merge(self):
        from homeassistant.components.lovelace.const import (
            CONF_REQUIRE_ADMIN,
            CONF_SHOW_IN_SIDEBAR,
            CONF_TITLE,
            CONF_URL_PATH,
        )

        import custom_components.kirkhill_wind.dashboard as dash

        hass = self._hass()
        default_config = {
            "views": [
                {
                    "title": "SCADA",
                    "cards": [
                        {"type": "entities", "title": "Owner data"},
                        {"type": "gauge", "title": "New in this version"},
                    ],
                }
            ]
        }
        user_card = {"type": "markdown", "content": "My notes"}
        existing_config = {
            "views": [
                {
                    "title": "SCADA",
                    "cards": [
                        {"type": "entities", "title": "Owner data"},
                        user_card,
                    ],
                }
            ]
        }
        existing_item = {
            CONF_URL_PATH: dash._URL_PATH,
            CONF_TITLE: "Kirk Hill Wind Farm",
            CONF_REQUIRE_ADMIN: False,
            CONF_SHOW_IN_SIDEBAR: True,
        }
        coll = _fake_collection(items=[existing_item])
        store = _fake_lovelace_store(existing=existing_config)
        with patch.object(
            dash.lovelace_dashboard, "DashboardsCollection"
        ) as coll_cls, patch.object(
            dash.lovelace_dashboard, "LovelaceStorage", return_value=store
        ), patch.object(
            dash, "build_dashboard_config", return_value=default_config
        ), patch.object(dash, "frontend"):
            coll_cls.return_value = coll
            await dash.async_ensure_dashboard(hass, self._entry())

        saved = store.async_save.call_args[0][0]
        # The user's own card survives inside the matched view, next to the
        # managed default (the merge's exact output shape is pinned in the
        # helper tests above).
        cards = saved["views"][0]["cards"]
        assert user_card in cards
        assert {"type": "entities", "title": "Owner data"} in cards
        assert {"type": "gauge", "title": "New in this version"} in cards
