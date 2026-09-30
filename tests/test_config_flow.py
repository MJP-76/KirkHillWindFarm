"""Tests for config flow — version consistency."""
from __future__ import annotations

from custom_components.kirkhill_wind import _CONFIG_ENTRY_VERSION
from custom_components.kirkhill_wind.config_flow import KirkHillWindConfigFlow


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
        """Version should be 8 (the current schema version).

        v8 split connection details from settings: entry.data keeps only the
        API key and base URL, and every user-configurable setting moved to
        entry.options.
        """
        assert KirkHillWindConfigFlow.VERSION == 8
