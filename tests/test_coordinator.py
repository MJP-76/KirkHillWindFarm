"""Tests for the coordinator — scheduling, auth errors, stale data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kirkhill_wind.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    SCOPE_OWNER,
    SCOPE_SITE,
    SCOPES,
)
from custom_components.kirkhill_wind.exceptions import (
    KirkHillApiError,
    KirkHillAuthError,
    KirkHillConnectionError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coordinator(hass, entry, mock_api_client):
    """Build a coordinator with a mocked API client."""
    from custom_components.kirkhill_wind.coordinator import KirkHillWindCoordinator

    with patch(
        "custom_components.kirkhill_wind.coordinator.KirkHillApiClient",
        return_value=mock_api_client,
    ):
        coord = KirkHillWindCoordinator(hass, entry)
    return coord


def _make_entry(data=None, options=None):
    """Return a fake config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = data or {
        CONF_API_KEY: "key",
        CONF_BASE_URL: DEFAULT_BASE_URL,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }
    entry.options = options or {}
    return entry


# ---------------------------------------------------------------------------
# Time-based scheduling
# ---------------------------------------------------------------------------

class TestTimeBasedScheduling:
    """Verify that medium and slow tiers use real time, not ticks."""

    @pytest.mark.asyncio
    async def test_first_poll_runs_all_tiers(self, hass, mock_api_client):
        """On the very first poll, turbine + slow tiers should run immediately."""
        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            await coord._async_update_data()

        # Turbine fetch should have been called (first poll = immediate)
        mock_api_client.get_turbines.assert_called()
        # Slow tier should have run (first poll = immediate)
        assert coord._next_slow_update > now

    @pytest.mark.asyncio
    async def test_turbine_tier_skipped_within_10min(self, hass, mock_api_client):
        """Turbine tier should NOT run if less than 10 minutes since last."""
        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # First poll — primes everything
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_turbines.reset_mock()

        # Second poll, 5 minutes later — turbine tier should be skipped
        t1 = t0 + timedelta(minutes=5)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t1,
        ):
            await coord._async_update_data()
        mock_api_client.get_turbines.assert_not_called()

    @pytest.mark.asyncio
    async def test_turbine_tier_runs_after_10min(self, hass, mock_api_client):
        """Turbine tier should run after 10 minutes have elapsed."""
        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_turbines.reset_mock()

        t1 = t0 + timedelta(minutes=11)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t1,
        ):
            await coord._async_update_data()
        mock_api_client.get_turbines.assert_called()

    @pytest.mark.asyncio
    async def test_slow_tier_skipped_within_1hr(self, hass, mock_api_client):
        """Slow tier (historical summaries) should NOT run within 1 hour."""
        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()

        # Check that slow timeframes were fetched on first poll
        first_slow_call_count = mock_api_client.get_summary.call_count

        t1 = t0 + timedelta(minutes=30)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t1,
        ):
            await coord._async_update_data()

        # Only fast timeframes (today) should have been fetched on second poll
        # — fewer calls than the first poll which included slow tiers.
        second_call_count = mock_api_client.get_summary.call_count - first_slow_call_count
        assert second_call_count < first_slow_call_count


# ---------------------------------------------------------------------------
# Auth error handling
# ---------------------------------------------------------------------------

class TestAuthErrorHandling:
    """Auth errors in any path must trigger ConfigEntryAuthFailed."""

    @pytest.mark.asyncio
    async def test_auth_error_on_current_triggers_reauth(self, hass, mock_api_client):
        """Auth failure on get_current raises ConfigEntryAuthFailed."""
        from homeassistant.config_entries import ConfigEntryAuthFailed

        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)
        mock_api_client.get_current = AsyncMock(
            side_effect=KirkHillAuthError("Invalid API key")
        )

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        ):
            with pytest.raises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_auth_error_on_summary_triggers_reauth(self, hass, mock_api_client):
        """Auth failure on get_summary raises ConfigEntryAuthFailed, not silent retry."""
        from homeassistant.config_entries import ConfigEntryAuthFailed

        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        # Make the summary fetch fail with an auth error while the current fetch succeeds
        async def summary_auth_fail(*args, **kwargs):
            raise KirkHillAuthError("Invalid API key")

        mock_api_client.get_summary = AsyncMock(side_effect=summary_auth_fail)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        ):
            with pytest.raises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_connection_error_marks_stale_and_retries(self, hass, mock_api_client):
        """Connection errors should mark data stale and schedule retry."""
        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        # Make summary fail with connection error
        mock_api_client.get_summary = AsyncMock(
            side_effect=KirkHillConnectionError("Timeout")
        )

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            await coord._async_update_data()

        # Should have recorded failures and scheduled retries
        assert len(coord._summary_failures) > 0
        assert len(coord._summary_retry_at) > 0
        # All stale flags should be True for failed scopes/timeframes
        for scope in SCOPES:
            for tf in coord._summary_stale.get(scope, {}):
                if (scope, tf) in coord._summary_failures:
                    assert coord._summary_stale[scope][tf] is True

    @pytest.mark.asyncio
    async def test_stale_data_retained_on_failure(self, hass, mock_api_client, mock_current_payload):
        """When current fetch fails, last-known-good data should be retained."""
        entry = _make_entry()
        coord = _make_coordinator(hass, entry, mock_api_client)

        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        # First poll — succeeds
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            result1 = await coord._async_update_data()

        # Second poll — API error on owner scope
        async def current_with_error(session, scope):
            if scope == SCOPE_OWNER:
                raise KirkHillApiError("Server error")
            return mock_current_payload

        mock_api_client.get_current = AsyncMock(side_effect=current_with_error)

        t1 = t0 + timedelta(seconds=60)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t1,
        ):
            result2 = await coord._async_update_data()

        # Owner data should still be present (retained from first poll)
        assert result2[SCOPE_OWNER] == result1[SCOPE_OWNER]
        # Owner scope should be marked stale
        assert result2["current_stale"][SCOPE_OWNER] is True
        # Site scope should NOT be stale
        assert result2["current_stale"][SCOPE_SITE] is False
