"""Tests for __init__.py — config entry migration."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kirkhill_wind import _CONFIG_ENTRY_VERSION, async_migrate_entry
from custom_components.kirkhill_wind.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    DEFAULT_BASE_URL,
    DEFAULT_CFD_PRICE_GBP_PER_MWH,
    DEFAULT_OWNER_PRICE_PENCE_PER_KWH,
)


class TestConfigMigration:
    """Verify config entry migration handles all version transitions."""

    def _make_entry(self, version, data, options=None):
        entry = MagicMock()
        entry.version = version
        entry.data = data
        entry.options = options or {}
        return entry

    @pytest.mark.asyncio
    async def test_already_current_version(self):
        """Migration should be a no-op when version is already current."""
        hass = MagicMock()
        entry = self._make_entry(_CONFIG_ENTRY_VERSION, {CONF_API_KEY: "key"})

        result = await async_migrate_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_migration_from_v1(self):
        """v1 -> current should add base_url and all new fields."""
        hass = MagicMock()
        entry = self._make_entry(1, {CONF_API_KEY: "key", "owner_share_percent": 50})

        result = await async_migrate_entry(hass, entry)
        assert result is True
        # Should have been updated to current version
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call[1]["data"] if update_call[1] else update_call[0][1]
        assert update_call[1]["version"] == _CONFIG_ENTRY_VERSION

    @pytest.mark.asyncio
    async def test_migration_from_v4_removes_dead_keys(self):
        """v4 -> current should remove owner_share_percent and owner_value_rate."""
        hass = MagicMock()
        entry = self._make_entry(4, {
            CONF_API_KEY: "key",
            CONF_BASE_URL: DEFAULT_BASE_URL,
            "owner_share_percent": 25,
            "owner_value_rate": 0.15,
        })

        result = await async_migrate_entry(hass, entry)
        assert result is True
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call[1]["data"]
        assert "owner_share_percent" not in updated_data
        assert "owner_value_rate" not in updated_data

    @pytest.mark.asyncio
    async def test_migration_from_v7_removes_projected_earnings(self):
        """v7 migration should remove projected earnings from data and options."""
        hass = MagicMock()
        entry = self._make_entry(7, {
            CONF_API_KEY: "key",
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_CFD_PRICE_GBP_PER_MWH: 50.0,
            CONF_OWNER_PRICE_PENCE_PER_KWH: 5.0,
            "owner_projected_annual_earnings_gbp": 1000,
            "site_projected_annual_earnings_gbp": 5000,
        }, options={
            "owner_projected_annual_earnings_gbp": 1200,
            "site_projected_annual_earnings_gbp": 5500,
        })

        result = await async_migrate_entry(hass, entry)
        assert result is True
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call[1]["data"]
        updated_options = update_call[1]["options"]
        assert "owner_projected_annual_earnings_gbp" not in updated_data
        assert "site_projected_annual_earnings_gbp" not in updated_data
        assert "owner_projected_annual_earnings_gbp" not in updated_options
        assert "site_projected_annual_earnings_gbp" not in updated_options


class TestManifestVersion:
    """Verify manifest version matches VERSION file."""

    def test_manifest_version_matches_version_file(self):
        import json
        from pathlib import Path

        root = Path(__file__).parent.parent
        manifest = json.loads((root / "custom_components/kirkhill_wind/manifest.json").read_text())
        version_file = (root / "VERSION").read_text().strip()

        assert manifest["version"] == version_file, (
            f"manifest.json version ({manifest['version']}) != "
            f"VERSION file ({version_file})"
        )