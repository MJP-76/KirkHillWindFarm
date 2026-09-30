"""Tests for the dashboard merge logic — the most fragile part of the integration."""
from __future__ import annotations

import copy

import pytest

from custom_components.kirkhill_wind import (
    _OBSOLETE_CARD_KEYS,
    _OBSOLETE_VIEW_PATHS,
    _card_match_key,
    _merge_cards,
    _merge_dashboard_config,
    _merge_view,
    _section_match_key,
)


# ---------------------------------------------------------------------------
# _card_match_key
# ---------------------------------------------------------------------------

class TestCardMatchKey:
    """Verify cards are matched by stable keys."""

    def test_heading_matched_by_text(self):
        assert _card_match_key({"type": "heading", "heading": "My Heading"}) == "heading:My Heading"

    def test_kpi_matched_by_name(self):
        card = {"type": "stat", "name": "Owner Power", "entity": "sensor.x"}
        assert _card_match_key(card) == "kpi:name:Owner Power"

    def test_kpi_falls_back_to_entity(self):
        card = {"type": "entity", "entity": "sensor.x"}
        assert _card_match_key(card) == "kpi:name:sensor.x"

    def test_entities_matched_by_title(self):
        card = {"type": "entities", "title": "Owner data"}
        assert _card_match_key(card) == "entities:title:Owner data"

    def test_button_matched_by_name(self):
        card = {"type": "button", "name": "Reload integration"}
        assert _card_match_key(card) == "button:name:Reload integration"

    def test_scada_card_matched_by_type(self):
        card = {"type": "custom:kirkhill-wind-scada", "title": ""}
        assert _card_match_key(card) == "custom:kirkhill-wind-scada"

    def test_apexcharts_matched_by_header_title(self):
        card = {"type": "custom:apexcharts-card", "header": {"title": "Wind"}}
        assert _card_match_key(card) == "custom:apexcharts-card:title:Wind"

    def test_unmatchable_card_returns_none(self):
        card = {"type": "custom:unknown"}
        assert _card_match_key(card) is None

    def test_container_matched_by_child_keys(self):
        card = {
            "type": "vertical-stack",
            "cards": [
                {"type": "heading", "heading": "Test"},
                {"type": "entities", "title": "Data"},
            ],
        }
        key = _card_match_key(card)
        assert key is not None
        assert "container:vertical-stack:" in key

    def test_card_type_not_included_in_kpi_key(self):
        """stat and entity cards with the same name should match."""
        stat = {"type": "stat", "name": "Power"}
        entity = {"type": "entity", "name": "Power"}
        assert _card_match_key(stat) == _card_match_key(entity)


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
        """Cards whose key is in _OBSOLETE_CARD_KEYS should be removed."""
        obsolete_key = next(iter(_OBSOLETE_CARD_KEYS))
        # Parse the key to reconstruct a minimal card
        # Keys look like "kpi:name:Owner Power" or "entities:title:Turbine T1"
        parts = obsolete_key.split(":", 2)
        if parts[0] == "kpi":
            existing = [{"type": "stat", "name": parts[2]}]
        elif parts[0] == "entities":
            existing = [{"type": "entities", "title": parts[2]}]
        else:
            existing = [{"type": parts[0], "title": parts[2]}]

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
# _merge_dashboard_config
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
        result = _merge_dashboard_config(existing, new)
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
        result = _merge_dashboard_config(existing, new)
        paths = [v["path"] for v in result["views"]]
        assert "my-custom-view" in paths

    def test_obsolete_view_removed(self):
        obsolete_path = next(iter(_OBSOLETE_VIEW_PATHS))
        existing = {
            "views": [
                {"path": obsolete_path, "cards": []},
            ],
        }
        new = {
            "views": [],
        }
        result = _merge_dashboard_config(existing, new)
        paths = [v.get("path") for v in result["views"]]
        assert obsolete_path not in paths

    def test_empty_existing_returns_default(self):
        new = {"views": [{"path": "scada", "cards": []}]}
        result = _merge_dashboard_config({}, new)
        assert result["views"][0]["path"] == "scada"