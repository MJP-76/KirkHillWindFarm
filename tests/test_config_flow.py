"""Tests for config flow — version consistency."""
from __future__ import annotations

import pytest

from custom_components.kirkhill_wind.config_flow import KirkHillWindConfigFlow
from custom_components.kirkhill_wind import _CONFIG_ENTRY_VERSION


class TestConfigFlowVersion:
    """Verify the config flow VERSION matches the migration target."""

    def test_version_matches_migration_target(self):
        """Config flow VERSION must equal _CONFIG_ENTRY_VERSION in __init__."""
        assert KirkHillWindConfigFlow.VERSION == _CONFIG_ENTRY_VERSION, (
            f"ConfigFlow.VERSION ({KirkHillWindConfigFlow.VERSION}) != "
            f"_CONFIG_ENTRY_VERSION ({_CONFIG_ENTRY_VERSION}). "
            f"New entries will need immediate migration."
        )

    def test_version_is_current(self):
        """Version should be 7 (the current schema version)."""
        assert KirkHillWindConfigFlow.VERSION == 7