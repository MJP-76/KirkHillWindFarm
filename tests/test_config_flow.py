"""Tests for config flow — version consistency and reauth."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kirkhill_wind import _CONFIG_ENTRY_VERSION, config_flow
from custom_components.kirkhill_wind.api import KirkHillApiClient
from custom_components.kirkhill_wind.config_flow import KirkHillWindConfigFlow
from custom_components.kirkhill_wind.const import CONF_API_KEY, DEFAULT_BASE_URL
from custom_components.kirkhill_wind.exceptions import (
    KirkHillAuthError,
    KirkHillPermissionError,
)


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


class TestPermissionGate:
    """A key that cannot read every scope must not create an entry.

    The integration always reads owner *and* site, so a key granted only one of
    them would produce an entry whose other sensors are dead from the first poll
    -- reported before this existed as a connection error.
    """

    @staticmethod
    def _make_flow(hass) -> KirkHillWindConfigFlow:
        flow = KirkHillWindConfigFlow()
        flow.hass = hass
        flow.flow_id = "flow-1"
        flow.handler = "kirkhill_wind"
        flow.context = {"source": "user"}
        flow._async_current_entries = MagicMock(return_value=[])
        return flow

    @pytest.mark.asyncio
    async def test_validate_maps_a_denied_scope_to_its_own_message(self, hass):
        flow = self._make_flow(hass)

        with (
            patch.object(config_flow, "async_get_clientsession", return_value=object()),
            patch.object(
                KirkHillApiClient,
                "test",
                side_effect=KirkHillPermissionError("403 for scope=site"),
            ),
        ):
            errors = await flow._validate_api_key("key", DEFAULT_BASE_URL)

        assert errors == {"base": "permission_required"}
        assert errors != {"base": "auth_failed"}, (
            "auth_failed would tell the user their key is invalid when it "
            "only lacks permission."
        )

    @pytest.mark.asyncio
    async def test_manual_path_refuses_the_key_with_that_message(self, hass):
        flow = self._make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "permission_required"})

        result = await flow.async_step_manual({CONF_API_KEY: "narrow-key"})

        assert result["type"] == "form"
        assert result["errors"] == {"base": "permission_required"}

    @pytest.mark.asyncio
    async def test_signin_aborts_with_the_consent_instructions(self, hass):
        flow = self._make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "permission_required"})

        result = await flow.async_oauth_create_entry(
            {"token": {"access_token": "kh_live_narrow"}}
        )

        assert result["type"] == "abort"
        assert result["reason"] == "oauth_permission_denied", (
            "oauth_key_invalid would blame the key instead of the consent choice."
        )


class TestValidationDetail:
    """A rejected key must leave its reason behind for the abort to quote."""

    @staticmethod
    def _make_flow(hass) -> KirkHillWindConfigFlow:
        flow = KirkHillWindConfigFlow()
        flow.hass = hass
        flow.flow_id = "flow-1"
        flow.handler = "kirkhill_wind"
        flow.context = {"source": "user"}
        flow._async_current_entries = MagicMock(return_value=[])
        return flow

    @pytest.mark.asyncio
    async def test_rejected_key_keeps_the_reason(self, hass):
        flow = self._make_flow(hass)

        with (
            patch.object(config_flow, "async_get_clientsession", return_value=object()),
            patch.object(
                KirkHillApiClient,
                "test",
                side_effect=KirkHillAuthError(
                    "Invalid or missing API key: The API key is not valid."
                ),
            ),
        ):
            errors = await flow._validate_api_key("key", DEFAULT_BASE_URL)

        assert errors == {"base": "auth_failed"}
        assert "not valid" in flow._validation_detail

    @pytest.mark.asyncio
    async def test_a_successful_validation_clears_the_detail(self, hass):
        flow = self._make_flow(hass)
        flow._validation_detail = "stale reason from a previous attempt"

        with (
            patch.object(config_flow, "async_get_clientsession", return_value=object()),
            patch.object(KirkHillApiClient, "test", return_value=None),
        ):
            errors = await flow._validate_api_key("key", DEFAULT_BASE_URL)

        assert errors == {}
        assert flow._validation_detail == ""
