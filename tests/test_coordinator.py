"""Tests for the coordinator — scheduling, auth errors, stale data."""

from __future__ import annotations

import asyncio
from collections import Counter
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
    TIMEFRAME_TO_RANGE,
    yearly_timeframes,
)
from custom_components.kirkhill_wind.exceptions import (
    KirkHillApiError,
    KirkHillAuthError,
    KirkHillConnectionError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(hass, entry, mock_api_client, now=None):
    """Build a coordinator with a mocked API client.

    ``now`` freezes dt_util.utcnow() while the coordinator is constructed.
    This matters: __init__ seeds _next_turbine_update/_next_slow_update from
    utcnow() so the first poll runs every tier. A test that only patches time
    around _async_update_data() leaves those timers set to the real (later)
    wall clock, so the patched "now" never reaches the interval and the
    medium/slow tiers silently never run.
    """
    from custom_components.kirkhill_wind.coordinator import KirkHillWindCoordinator

    with patch(
        "custom_components.kirkhill_wind.coordinator.KirkHillApiClient",
        return_value=mock_api_client,
    ):
        if now is None:
            return KirkHillWindCoordinator(hass, entry)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            return KirkHillWindCoordinator(hass, entry)


def _make_entry(data=None, options=None):
    """Return a fake config entry.

    Mirrors the v8 split: connection details in data, settings in options.
    """
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = data or {
        CONF_API_KEY: "key",
        CONF_BASE_URL: DEFAULT_BASE_URL,
    }
    entry.options = (
        options
        if options is not None
        else {
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        }
    )
    return entry


def _summary_calls(mock_api_client):
    """Return {(scope, range_value): fetch_count} for one coordinator update.

    Deliberately a Counter, not a set. A set collapses duplicates, so it cannot
    express the property we actually care about -- that a timeframe is fetched
    exactly once -- and it let a doubled summary fetch ship to production in
    v4.13.4. Keys are (scope, range_value) as the coordinator calls the API;
    the coordinator's internal timeframe names ("alltime", "week", "month")
    map to range values ("all", "7d", "30d") before they get here.
    """
    counter = Counter(
        (call.kwargs["scope"], call.kwargs["range_value"]) for call in mock_api_client.get_summary.call_args_list
    )
    return dict(counter)


def _current_year():
    """The calendar year the coordinator will use for the `year` timeframe.

    _fetch_timeframe_summaries reads dt_util.now().year -- the *real* wall
    clock, not the utcnow() a test patches. A test that hardcodes a year goes
    stale every January, so derive it the same way production does.
    """
    from homeassistant.util import dt as dt_util

    return dt_util.now().year


def _ranges_for(timeframes):
    """Map timeframe keys to the range values the API is called with.

    Derived from the production tables rather than hardcoded so these tests do
    not rot when a timeframe is added. Note SLOW_TIMEFRAMES does *not* contain
    "today" -- the fast tier is a separate tuple, and a due slow poll fetches
    the union of both.
    """
    current_year = _current_year()
    return {str(current_year) if tf == "year" else TIMEFRAME_TO_RANGE[tf] for tf in timeframes}


def _fast_ranges():
    """Range values fetched on any poll: the fast tier."""
    from custom_components.kirkhill_wind.coordinator import FAST_TIMEFRAMES

    return _ranges_for(FAST_TIMEFRAMES)


def _rolling_ranges():
    """Range values fetched when the slow tier is also due (fast + slow)."""
    from custom_components.kirkhill_wind.coordinator import FAST_TIMEFRAMES, SLOW_TIMEFRAMES

    return _ranges_for(FAST_TIMEFRAMES + SLOW_TIMEFRAMES)


def _past_year_ranges():
    """Range values for the completed-year timeframes, once they exist.

    On a machine whose clock is before 2026 there are no completed years yet,
    so return empty rather than asserting against a fiction.
    """
    return {tf.split("_", 1)[1] for tf in yearly_timeframes()}


# ---------------------------------------------------------------------------
# Time-based scheduling
# ---------------------------------------------------------------------------


class TestTimeBasedScheduling:
    """Verify that medium and slow tiers use real time, not ticks."""

    @pytest.mark.asyncio
    async def test_first_poll_runs_all_tiers(self, hass, mock_api_client):
        """On the very first poll, turbine + slow tiers should run immediately."""
        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        await coord._async_update_data()

        # Turbine fetch should have been called (first poll = immediate)
        mock_api_client.get_turbines.assert_called()
        # Both tiers should have rescheduled themselves into the future
        assert coord._next_turbine_update > now
        assert coord._next_slow_update > now

    @pytest.mark.asyncio
    async def test_turbine_tier_skipped_within_10min(self, hass, mock_api_client):
        """Turbine tier should NOT run if less than 10 minutes since last."""
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        # First poll — primes everything
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_turbines.assert_called()
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
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_turbines.assert_called()
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
        """Slow tier (historical summaries) should NOT re-run within 1 hour."""
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()

        # First poll runs the fast and slow tiers for both scopes. Note the
        # coordinator passes API range values ("all", "7d", "30d"), not the
        # internal timeframe names ("alltime", "week", "month").
        first_poll = _summary_calls(mock_api_client)
        assert (SCOPE_OWNER, "7d") in first_poll
        assert (SCOPE_SITE, "all") in first_poll
        # Cardinality matters as much as membership: a set is invariant under
        # duplication, which is how the doubled summary fetch shipped. Every
        # (scope, range) pair must appear exactly once.
        assert set(first_poll.values()) == {1}, (
            "a (scope, range) pair was fetched more than once on the first poll: "
            f"{ {k: v for k, v in first_poll.items() if v != 1} }"
        )

        mock_api_client.get_summary.reset_mock()

        t1 = t0 + timedelta(minutes=30)
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t1,
        ):
            await coord._async_update_data()

        # Within the hour only the fast 'today' timeframe is re-fetched, for
        # both scopes -- once each, not twice.
        second_poll = _summary_calls(mock_api_client)
        assert second_poll == {(SCOPE_OWNER, "today"): 1, (SCOPE_SITE, "today"): 1}


class TestApiCallBudget:
    """The coordinator is designed around API request frequency, so pin it.

    A doubled summary fetch shipped in v4.13.4 because the schedule test
    asserted a *set* of (scope, range) pairs. A set is invariant under
    duplication -- it yields the same value whether a timeframe is fetched once
    or twice. These tests assert counts, so they fail if any pair is fetched
    more than once.
    """

    @staticmethod
    def _only_once(calls, label):
        offenders = {k: v for k, v in calls.items() if v != 1}
        assert not offenders, (
            f"{label}: expected every (scope, range) fetched exactly once, but these were duplicated: {offenders}"
        )

    @pytest.mark.asyncio
    async def test_summaries_are_fetched_exactly_once_per_update(self, hass, mock_api_client):
        """Named in coordinator.py: no (scope, range) pair may be fetched twice.

        This is the regression test for the v4.13.4 bug. The summary fetch ran
        both in the initial asyncio.gather and again after the turbine tier;
        because _next_slow_update is advanced only *after* the later call, the
        earlier one also saw the slow tier as due and re-fetched every
        timeframe. Every tier due on the first poll is therefore the worst
        case, and the exact key set is asserted so a *newly added* timeframe is
        also caught if it is somehow fetched twice.
        """
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()

        calls = _summary_calls(mock_api_client)

        # Every tier is due on the first poll: the rolling ranges, the current
        # year, and each completed year (none cached yet).
        expected = {(scope, range_value) for scope in SCOPES for range_value in _rolling_ranges() | _past_year_ranges()}
        assert set(calls) == expected, (
            "first poll must fetch every timeframe exactly once per scope; "
            f"missing={expected - set(calls)} unexpected={set(calls) - expected}"
        )
        self._only_once(calls, "first poll (all tiers due)")

    @pytest.mark.asyncio
    async def test_fast_poll_fetches_today_once_per_scope(self, hass, mock_api_client):
        """A steady-state poll must fetch exactly one summary per scope."""
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        # Prime: first poll runs every tier and caches completed years.
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_summary.reset_mock()
        mock_api_client.get_current.reset_mock()

        # Steady-state fast poll, 5 minutes later: slow and turbine tiers off.
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0 + timedelta(minutes=5),
        ):
            await coord._async_update_data()

        assert mock_api_client.get_current.call_count == 2  # owner + site
        fast = {(scope, r): 1 for scope in SCOPES for r in _fast_ranges()}
        assert _summary_calls(mock_api_client) == fast, (
            "a steady-state poll must fetch exactly the fast tier, once per scope"
        )
        self._only_once(_summary_calls(mock_api_client), "fast poll")

    @pytest.mark.asyncio
    async def test_turbine_due_poll_adds_no_extra_summaries(self, hass, mock_api_client):
        """A turbine-due poll fetches turbines, but summaries stay at today-once."""
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_summary.reset_mock()
        mock_api_client.get_turbines.reset_mock()

        # 11 minutes: turbine tier due, slow tier still not.
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0 + timedelta(minutes=11),
        ):
            await coord._async_update_data()

        # Two turbine calls: range=today and range=all.
        assert mock_api_client.get_turbines.call_count == 2
        fast = {(scope, r): 1 for scope in SCOPES for r in _fast_ranges()}
        assert _summary_calls(mock_api_client) == fast, (
            "a turbine-due poll must not add summaries -- the slow tier is not due"
        )
        self._only_once(_summary_calls(mock_api_client), "turbine-due poll")

    @pytest.mark.asyncio
    async def test_slow_tier_fetches_each_timeframe_once_per_scope(self, hass, mock_api_client):
        """A slow-tier poll must not double-fetch the historical timeframes.

        The completed years were cached on the first poll, so a due slow tier
        must request only the rolling ranges -- once each per scope.
        """
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()
        mock_api_client.get_summary.reset_mock()

        # 61 minutes: slow tier due again, turbine tier long expired but
        # irrelevant to summaries.
        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0 + timedelta(minutes=61),
        ):
            await coord._async_update_data()

        calls = _summary_calls(mock_api_client)
        self._only_once(calls, "slow-tier poll")

        rolling = _rolling_ranges()
        assert set(calls) == {(scope, r) for scope in SCOPES for r in rolling}, (
            "a due slow tier must fetch exactly the rolling ranges -- completed "
            f"years are cached. missing={ {(s, r) for s in SCOPES for r in rolling} - set(calls) } "
            f"unexpected={set(calls) - {(s, r) for s in SCOPES for r in rolling}}"
        )

        # Explicitly: completed years must not be requested again.
        for scope in SCOPES:
            for year in _past_year_ranges():
                assert (scope, year) not in calls, f"completed year {year} was re-requested for {scope}"

    @pytest.mark.asyncio
    async def test_completed_years_are_fetched_once_ever(self, hass, mock_api_client):
        """Completed calendar years are cached and never re-requested."""
        entry = _make_entry()
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=t0,
        ):
            await coord._async_update_data()

        past_years = _past_year_ranges()
        if not past_years:
            pytest.skip("no completed calendar year to cache on this clock")

        first = _summary_calls(mock_api_client)
        for scope in SCOPES:
            for year in past_years:
                assert first.get((scope, year)) == 1, (
                    f"first poll must fetch completed year {year} for {scope} "
                    f"exactly once, got {first.get((scope, year))}"
                )

        # Two further slow-tier polls over the following two hours. Each poll is
        # counted separately: the Counter accumulates across polls, so combining
        # them would report every range as fetched twice and prove nothing.
        for minutes in (61, 121):
            mock_api_client.get_summary.reset_mock()
            with patch(
                "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
                return_value=t0 + timedelta(minutes=minutes),
            ):
                await coord._async_update_data()

            later = _summary_calls(mock_api_client)
            for scope in SCOPES:
                for year in past_years:
                    assert (scope, year) not in later, (
                        f"completed year {year} was re-requested for {scope} {minutes} minutes in"
                    )
            self._only_once(later, f"slow poll at +{minutes}min")


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
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)
        mock_api_client.get_current = AsyncMock(side_effect=KirkHillAuthError("Invalid API key"))

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            with pytest.raises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_auth_error_on_summary_triggers_reauth(self, hass, mock_api_client):
        """Auth failure on get_summary raises ConfigEntryAuthFailed, not silent retry."""
        from homeassistant.config_entries import ConfigEntryAuthFailed

        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        # Make the summary fetch fail with an auth error while the current fetch succeeds
        async def summary_auth_fail(*args, **kwargs):
            raise KirkHillAuthError("Invalid API key")

        mock_api_client.get_summary = AsyncMock(side_effect=summary_auth_fail)

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            with pytest.raises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_connection_error_marks_stale_and_retries(self, hass, mock_api_client):
        """Connection errors should mark data stale and schedule retry."""
        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        # Make summary fail with connection error
        mock_api_client.get_summary = AsyncMock(side_effect=KirkHillConnectionError("Timeout"))

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
        t0 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=t0)

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


# ---------------------------------------------------------------------------
# Forecast task lifecycle
# ---------------------------------------------------------------------------


class TestForecastTaskLifecycle:
    """The slow-tier forecast task must not outlive the update that created it."""

    @pytest.mark.asyncio
    async def test_forecast_task_is_reaped_when_summary_fetch_raises(self, hass, mock_api_client):
        """A failing summary fetch cancels the forecast instead of orphaning it.

        _fetch_timeframe_summaries re-raises ConfigEntryAuthFailed (a 401 on any
        summary), which used to strand forecast_task: it kept running its retry
        sleeps in the background while asyncio reported "Task was destroyed but
        it is pending".
        """
        from homeassistant.config_entries import ConfigEntryAuthFailed

        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        cancelled = asyncio.Event()

        async def hanging_forecast(session, coordinates):
            # Never returns on its own, so an unreaped task stays pending.
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        coord._fetch_open_meteo_forecast = hanging_forecast
        mock_api_client.get_summary = AsyncMock(side_effect=KirkHillAuthError("Invalid API key"))

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            with pytest.raises(ConfigEntryAuthFailed):
                await coord._async_update_data()

        assert cancelled.is_set(), "the Open-Meteo forecast task was left running after the update failed"
        assert coord._next_slow_update == now, "a failed update must not consume the slow-tier slot"

    @pytest.mark.asyncio
    async def test_forecast_result_is_consumed_on_success(self, hass, mock_api_client):
        """The happy path still awaits the forecast and advances the slow timer."""
        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        async def quick_forecast(session, coordinates):
            return {"provider": "open_meteo", "next_hour_wind_speed_mps": 7.5}

        coord._fetch_open_meteo_forecast = quick_forecast

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            data = await coord._async_update_data()

        assert data["open_meteo_forecast"]["provider"] == "open_meteo"
        assert coord._next_slow_update == now + timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_forecast_exception_does_not_fail_the_update(self, hass, mock_api_client):
        """A forecast it cannot parse must not take the whole update down.

        _fetch_open_meteo_forecast says "never fail core update", but its
        except tuple misses ValueError/AttributeError, so the exception used to
        surface at `await forecast_task` and every entity went unavailable for
        a poll because a third-party payload was malformed.
        """
        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        async def exploding_forecast(session, coordinates):
            raise ValueError("malformed forecast payload")

        coord._fetch_open_meteo_forecast = exploding_forecast

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            data = await coord._async_update_data()

        assert data["open_meteo_forecast"] == {}
        assert coord._next_slow_update == now + timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_forecast_task_is_reaped_when_the_update_is_cancelled(self, hass, mock_api_client):
        """Tearing the update down mid-forecast must not strand the task."""
        entry = _make_entry()
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        coord = _make_coordinator(hass, entry, mock_api_client, now=now)

        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def hanging_forecast(session, coordinates):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        coord._fetch_open_meteo_forecast = hanging_forecast

        with patch(
            "custom_components.kirkhill_wind.coordinator.dt_util.utcnow",
            return_value=now,
        ):
            update = asyncio.create_task(coord._async_update_data())
            await asyncio.wait_for(started.wait(), timeout=5)
            update.cancel()
            with pytest.raises(asyncio.CancelledError):
                await update

        assert cancelled.is_set(), "the Open-Meteo forecast task outlived the update that created it"
