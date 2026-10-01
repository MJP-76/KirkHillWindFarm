"""Coordinator for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import KirkHillApiClient, OpenMeteoApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
    SCOPE_OWNER,
    SCOPE_SITE,
    SCOPES,
    TIMEFRAME_TO_RANGE,
    yearly_timeframes,
)
from .exceptions import KirkHillApiError, KirkHillAuthError
from .settings import get_scan_interval

_LOGGER = logging.getLogger(__name__)

# Tiered update intervals (real time, independent of poll interval)
# Fast: every poll - current power + today summary
# Medium: every 10 minutes - turbines, wind-speed series
# Slow: every 1 hour - yesterday, week, month, ytd, year, alltime,
#       past-year CfD windows (year_YYYY), Open-Meteo forecast
FAST_TIMEFRAMES = ("today",)
SLOW_TIMEFRAMES = ("yesterday", "week", "month", "ytd", "year", "alltime")
_TURBINE_INTERVAL = timedelta(minutes=10)
_SLOW_INTERVAL = timedelta(hours=1)


class KirkHillWindCoordinator(DataUpdateCoordinator):
    """Fetches current data from owner/site scopes on each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        scan_interval = get_scan_interval(entry)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.entry = entry
        self.client = KirkHillApiClient(
            api_key=entry.data[CONF_API_KEY],
            base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        )
        self.open_meteo_client = OpenMeteoApiClient()
        # Time-based scheduling: initialise to "now" so the first tick runs
        # all tiers immediately, after which each tier resets its own timer.
        now = dt_util.utcnow()
        self._next_turbine_update: datetime = now
        self._next_slow_update: datetime = now
        self._site_turbines: list[dict] = []
        self._turbine_generation: dict[str, dict] = {}
        self._open_meteo_forecast: dict = {}
        # Immutable year summaries: completed calendar years never change, so
        # fetch them once and cache forever.  Keyed by (scope, year_string).
        self._immutable_year_summaries: dict[tuple[str, str], dict] = {}
        self._immutable_year_windows: dict[tuple[str, str], dict] = {}
        # Last known-good current payloads per scope, kept so a failed fast-path
        # refresh keeps showing old data (marked stale) instead of blanking.
        self._last_current: dict[str, dict] = {}
        self._current_stale: dict[str, bool] = {scope: False for scope in SCOPES}
        # Last known-good summaries/windows per (scope, timeframe), kept so a
        # failed refresh keeps showing old data (marked stale) instead of blanking.
        self._last_summaries: dict[str, dict[str, dict]] = {scope: {} for scope in SCOPES}
        self._last_windows: dict[str, dict[str, dict]] = {scope: {} for scope in SCOPES}
        # Backoff retry state: consecutive failure count and the UTC time at
        # which a (scope, timeframe) should be retried again after a failure.
        self._summary_failures: dict[tuple[str, str], int] = {}
        self._summary_retry_at: dict[tuple[str, str], datetime] = {}
        self._summary_stale: dict[str, dict[str, bool]] = {
            scope: {} for scope in SCOPES
        }

    def apply_options(self) -> None:
        """Re-apply scan interval when options change."""
        self.update_interval = timedelta(seconds=get_scan_interval(self.entry))

    async def _async_update_data(self) -> dict:
        """Fetch current owner/site data, turbine coordinates, and range summaries."""
        now = dt_util.utcnow()
        # One shared session for the integration's lifetime (HA-managed), instead
        # of a fresh session + connection pool on every poll.
        session = async_get_clientsession(self.hass)

        # Fast tier: current owner/site payloads are fetched every tick alongside
        # the today summary. Results are collected with return_exceptions so a
        # failure in one scope keeps the other scope (and the summary tier)
        # refreshing instead of blanking the whole update.
        owner_result: Any
        site_result: Any
        timeframe_result: Any
        owner_result, site_result, timeframe_result = await asyncio.gather(
            self.client.get_current(session, SCOPE_OWNER),
            self.client.get_current(session, SCOPE_SITE),
            self._fetch_timeframe_summaries(session, now),
            return_exceptions=True,
        )
        owner_data = self._resolve_current_result(SCOPE_OWNER, owner_result)
        site_data = self._resolve_current_result(SCOPE_SITE, site_result)
        if isinstance(timeframe_result, BaseException):
            # Only an unexpected error can escape _fetch_timeframe_summaries;
            # per-timeframe API failures are absorbed inside it.
            raise timeframe_result
        timeframe_summaries, timeframe_windows = timeframe_result

        # Medium tier: turbines + today's wind-speed series (every 10 minutes)
        if now >= self._next_turbine_update:
            try:
                today_turbines, alltime_turbines = await asyncio.gather(
                    self.client.get_turbines(session, SCOPE_SITE, range_value="today"),
                    self.client.get_turbines(session, SCOPE_SITE, range_value="all"),
                )
            except KirkHillAuthError as exc:
                raise ConfigEntryAuthFailed(str(exc)) from exc
            except KirkHillApiError as exc:
                # Keep the previous turbine map/generation data on a transient
                # failure instead of losing the whole tick; coordinates from the
                # last good fetch stay available for the map.
                _LOGGER.warning("Failed to fetch turbine data (keeping last known): %s", exc)
            else:
                self._site_turbines = today_turbines
                self._turbine_generation = self._build_turbine_generation(
                    today_turbines, alltime_turbines
                )
            self._next_turbine_update = now + _TURBINE_INTERVAL

        coordinates: dict[str, dict[str, float | str | None]] = {}
        for row in self._site_turbines:
            turbine_id = row.get("id")
            coord = row.get("coordinates") or {}
            if turbine_id:
                coordinates[turbine_id] = {
                    "latitude": coord.get("latitude"),
                    "longitude": coord.get("longitude"),
                    "source": coord.get("source"),
                    "openstreetmap_node_id": coord.get("openstreetmap_node_id"),
                }

        # Slow tier: Open-Meteo forecast (every 1 hour)
        if now >= self._next_slow_update:
            self._open_meteo_forecast = await self._fetch_open_meteo_forecast(session, coordinates)
            self._next_slow_update = now + _SLOW_INTERVAL

        return {
            SCOPE_OWNER: owner_data,
            SCOPE_SITE: site_data,
            "coordinates": self._last_coordinates(),
            "timeframe_summaries": timeframe_summaries,
            "timeframe_windows": timeframe_windows,
            "summary_stale": self._summary_stale,
            "current_stale": dict(self._current_stale),
            "turbine_generation": self._turbine_generation,
            "open_meteo_forecast": self._open_meteo_forecast,
            "summary_failures": {
                f"{scope}:{timeframe}": count
                for (scope, timeframe), count in self._summary_failures.items()
            },
            "summary_retry_at": {
                f"{scope}:{timeframe}": retry_at.isoformat()
                for (scope, timeframe), retry_at in self._summary_retry_at.items()
            },
        }

    def _resolve_current_result(self, scope: str, result: Any) -> dict:
        """Return the current payload for a scope, retaining the last known on failure.

        API-level failures flip the scope's stale flag but keep the last good
        data flowing — mirroring the per-timeframe summary fallback. Auth
        failures and unexpected errors still propagate so HA can prompt re-auth
        or surface a genuine bug.
        """
        if isinstance(result, Exception):
            if isinstance(result, KirkHillAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if not isinstance(result, KirkHillApiError):
                raise result
            _LOGGER.warning(
                "Failed to fetch current data for scope=%s: %s "
                "(keeping last known data, marked stale)",
                scope,
                result,
            )
            self._current_stale[scope] = True
            return self._last_current.get(scope, {})
        self._current_stale[scope] = False
        self._last_current[scope] = result
        return result

    def _last_coordinates(self) -> dict[str, dict[str, float | str | None]]:
        """Return the turbine coordinates built from the current turbine set."""
        coordinates: dict[str, dict[str, float | str | None]] = {}
        for row in self._site_turbines:
            turbine_id = row.get("id")
            coord = row.get("coordinates") or {}
            if turbine_id:
                coordinates[turbine_id] = {
                    "latitude": coord.get("latitude"),
                    "longitude": coord.get("longitude"),
                    "source": coord.get("source"),
                    "openstreetmap_node_id": coord.get("openstreetmap_node_id"),
                }
        return coordinates

    def _build_turbine_generation(
        self, today: list[dict], alltime: list[dict]
    ) -> dict[str, dict]:
        """Build a per-turbine generation/rotor map from the turbines API responses."""
        result: dict[str, dict] = {}
        for t in today:
            turbine_id = t.get("id")
            if not turbine_id:
                continue
            result[turbine_id] = {
                "generation_today_kwh": t.get("generation_kwh"),
                "generation_today_share_percent": t.get("generation_share_percent"),
                "rotor_speed_rpm": t.get("latest_rotor_speed_rpm"),
                "rotor_speed_at": t.get("latest_rotor_speed_at"),
            }
        for t in alltime:
            turbine_id = t.get("id")
            if turbine_id and turbine_id in result:
                result[turbine_id]["generation_alltime_kwh"] = t.get("generation_kwh")
                result[turbine_id]["generation_alltime_share_percent"] = t.get(
                    "generation_share_percent"
                )
        return result

    async def _fetch_timeframe_summaries(
        self, session: aiohttp.ClientSession, now: datetime
    ) -> tuple[dict[str, dict[str, dict]], dict[str, dict[str, dict]]]:
        tasks: list[tuple[str, str, asyncio.Task]] = []
        current_year = dt_util.now().year

        # Seed summaries/windows with cached immutable year data.  Completed
        # calendar years never change, so fetch them once and reuse forever.
        summaries: dict[str, dict[str, dict]] = {
            scope: dict(self._last_summaries[scope]) for scope in SCOPES
        }
        windows: dict[str, dict[str, dict]] = {
            scope: dict(self._last_windows[scope]) for scope in SCOPES
        }
        for (scope, year_str), cached in self._immutable_year_summaries.items():
            summaries[scope][f"year_{year_str}"] = cached
        for (scope, year_str), cached in self._immutable_year_windows.items():
            windows[scope][f"year_{year_str}"] = cached

        # Determine which timeframes to fetch this poll. The slow tier runs
        # when the caller's timestamp passes the slow timer; retries use a
        # real-UTC backoff schedule independent of the poll interval.
        timeframes: set[str] = set(FAST_TIMEFRAMES)
        run_slow = now >= self._next_slow_update
        if run_slow:
            timeframes.update(SLOW_TIMEFRAMES)
            # Past calendar years (year_YYYY) — derived so future years are
            # fetched automatically as they complete.
            timeframes.update(yearly_timeframes())
        for (scope, timeframe), retry_at in list(self._summary_retry_at.items()):
            if now >= retry_at:
                timeframes.add(timeframe)
                # Clear the retry entry so a successful fetch below resets it.
        _LOGGER.debug("Fetching summaries for timeframes=%s (slow_tier=%s)", sorted(timeframes), run_slow)

        for scope in SCOPES:
            for timeframe in sorted(timeframes):
                if timeframe == "year":
                    range_value = str(current_year)
                elif timeframe.startswith("year_"):
                    year_str = timeframe.split("_")[1]
                    range_value = year_str
                    # Completed years are immutable — skip if already cached.
                    if int(year_str) < current_year and (scope, year_str) in self._immutable_year_summaries:
                        continue
                else:
                    range_value = TIMEFRAME_TO_RANGE[timeframe]
                task = asyncio.create_task(
                    self.client.get_summary(session, scope=scope, range_value=range_value)
                )
                tasks.append((scope, timeframe, task))

        results = await asyncio.gather(
            *(task for _, _, task in tasks),
            return_exceptions=True,
        )

        for (scope, timeframe, _), payload in zip(tasks, results):
            key = (scope, timeframe)
            if isinstance(payload, BaseException):
                # Auth errors must trigger HA's reauth flow, not just retry.
                if isinstance(payload, KirkHillAuthError):
                    raise ConfigEntryAuthFailed(str(payload)) from payload
                failures = self._summary_failures.get(key, 0) + 1
                self._summary_failures[key] = failures
                # Backoff: retry after 1m, 2m, 4m, ... capped at 1 hour so we
                # never hammer the API during an outage.
                backoff = min(60 * (2 ** (failures - 1)), 3600)
                retry_at = now + timedelta(seconds=backoff)
                self._summary_retry_at[key] = retry_at
                self._summary_stale[scope][timeframe] = True
                _LOGGER.warning(
                    "Failed to fetch summary for scope=%s timeframe=%s: %s "
                    "(keeping last known data, marked stale; next retry at %s)",
                    scope,
                    timeframe,
                    payload,
                    retry_at.isoformat(),
                )
                # Keep the last good values instead of blanking the dashboard.
                summaries[scope][timeframe] = self._last_summaries[scope].get(timeframe, {})
                windows[scope][timeframe] = self._last_windows[scope].get(timeframe, {})
                continue

            summary = payload.get("summary")
            summary_out = summary if isinstance(summary, dict) else {}
            window = payload.get("window")
            window_out = window if isinstance(window, dict) else {}
            _LOGGER.debug(
                "Fetched summary scope=%s timeframe=%s stale_data=%s failures_prev=%s",
                scope,
                timeframe,
                self._summary_stale[scope].get(timeframe, False),
                self._summary_failures.get(key, 0),
            )
            summaries[scope][timeframe] = summary_out
            windows[scope][timeframe] = window_out
            self._last_summaries[scope][timeframe] = summary_out
            self._last_windows[scope][timeframe] = window_out
            self._summary_failures.pop(key, None)
            self._summary_retry_at.pop(key, None)
            self._summary_stale[scope][timeframe] = False
            # Cache completed year data — it never changes.
            if timeframe.startswith("year_") and int(timeframe.split("_")[1]) < current_year:
                self._immutable_year_summaries[(scope, timeframe.split("_")[1])] = summary_out
                self._immutable_year_windows[(scope, timeframe.split("_")[1])] = window_out

        return summaries, windows

    async def _fetch_open_meteo_forecast(
        self,
        session: aiohttp.ClientSession,
        coordinates: dict[str, dict[str, float | str | None]],
    ) -> dict:
        """Fetch optional Open-Meteo forecast; never fail core update."""

        latitude, longitude = self._resolve_forecast_location(coordinates)
        if latitude is None or longitude is None:
            return {}

        last_exc = None

        for attempt in range(3):
            try:
                forecast = await self.open_meteo_client.get_point_forecast(
                    session,
                    latitude=latitude,
                    longitude=longitude,
                )
            except (aiohttp.ClientError, asyncio.TimeoutError, KirkHillApiError) as exc:
                last_exc = exc
                if attempt < 2:
                    # Short exponential backoff between attempts — same spirit
                    # as the summary retry schedule, but bounded within this tick.
                    await asyncio.sleep(2**attempt)
            else:
                return forecast

        _LOGGER.warning(
            "Open-Meteo forecast fetch failed (forecast-only, non-fatal): %s",
            last_exc,
        )
        return {}

    def _resolve_forecast_location(
        self, coordinates: dict[str, dict[str, float | str | None]]
    ) -> tuple[float | None, float | None]:
        """Resolve forecast location from turbine coordinates automatically."""
        latitudes: list[float] = []
        longitudes: list[float] = []
        for coord in coordinates.values():
            lat = coord.get("latitude")
            lon = coord.get("longitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                latitudes.append(float(lat))
                longitudes.append(float(lon))

        if not latitudes or not longitudes:
            return None, None

        return sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)
