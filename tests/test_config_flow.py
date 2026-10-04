"""Tests for config flow — version consistency and reauth."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.kirkhill_wind import _CONFIG_ENTRY_VERSION
from custom_components.kirkhill_wind.config_flow import KirkHillWindConfigFlow
from custom_components.kirkhill_wind.const import CONF_API_KEY


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
        """Version should be 9 (the current schema version).

        v8 split connection details from settings: entry.data keeps only the
        API key and base URL, and every user-configurable setting moved to
        entry.options.

        v9 adds the price-backfill marker, so prices set before v4.13.0 can be
        recovered from restore_state on the next start.
        """
        assert KirkHillWindConfigFlow.VERSION == 9


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {CONF_API_KEY: "old-key"}
    return entry


def _make_reauth_flow(hass, entry: MagicMock, *, validate_errors: dict) -> KirkHillWindConfigFlow:
    """Build a reauth flow wired to mocks instead of a live HA instance."""
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    def _fake_update(target, *, data=None, **kwargs):
        # async_update_entry replaces entry.data wholesale.
        if data is not None:
            target.data = dict(data)

    hass.config_entries.async_update_entry = MagicMock(side_effect=_fake_update)

    flow = KirkHillWindConfigFlow()
    flow.hass = hass
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}
    flow._validate_api_key = AsyncMock(return_value=validate_errors)
    flow.async_abort = MagicMock(side_effect=lambda reason: {"type": "abort", "reason": reason})
    flow.async_show_form = MagicMock(
        side_effect=lambda step_id, errors=None, **kwargs: {"type": "form", "errors": errors}
    )
    return flow


class TestReauth:
    """A completed reauth must actually put the new key to work.

    The coordinator captures entry.data[CONF_API_KEY] when it builds its API
    client, so writing entry.data alone changes nothing at runtime -- see
    TestUpdateListenerReloadDecision in test_init.py for the reload half.
    """

    @pytest.mark.asyncio
    async def test_valid_key_is_written_to_entry_data(self, hass):
        entry = _make_entry()
        flow = _make_reauth_flow(hass, entry, validate_errors={})

        result = await flow.async_step_reauth({CONF_API_KEY: "new-key"})

        assert result == {"type": "abort", "reason": "reauth_successful"}
        assert entry.data[CONF_API_KEY] == "new-key", (
            "The reauth'd key never reached entry.data, so the coordinator "
            "would keep polling with the stale key and re-prompt forever."
        )
        hass.config_entries.async_update_entry.assert_called_once()
        # The flow must not reload the entry itself: the entry has update
        # listeners, and HA reports usage when a flow reloads such an entry
        # (an error from 2026.12). The listener schedules it instead.
        hass.config_entries.async_schedule_reload.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejected_key_leaves_the_entry_untouched(self, hass):
        entry = _make_entry()
        flow = _make_reauth_flow(hass, entry, validate_errors={"base": "auth_failed"})

        result = await flow.async_step_reauth({CONF_API_KEY: "bad-key"})

        assert result["type"] == "form"
        assert result["errors"] == {"base": "auth_failed"}
        assert entry.data[CONF_API_KEY] == "old-key"
        hass.config_entries.async_update_entry.assert_not_called()
        hass.config_entries.async_schedule_reload.assert_not_called()
