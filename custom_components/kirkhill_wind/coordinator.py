"""Coordinator for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
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
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCOPE_OWNER,
    SCOPE_SITE,
    SCOPES,
    TIMEFRAME_TO_RANGE,
)
from .exceptions import KirkHillApiError, KirkHillAuthError

_LOGGER = logging.getLogger(__name__)

# Tiered update intervals (in coordinator ticks; tick 1 primes everything)
# Fast: every poll - current power + today summary
# Slow: every 60 polls (~1 hour) - yesterday (static once day ends), week, month, ytd, year, alltime
#       + Open-Meteo forecast, turbine data, wind-speed series
FAST_TIMEFRAMES = ("today",)
SLOW_TIMEFRAMES = ("yesterday", "week", "month", "ytd", "year", "alltime")


class KirkHillWindCoordinator(DataUpdateCoordinator):
    """Fetches current data from owner/site scopes on each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.client = KirkHillApiClient(
            api_key=entry.data[CONF_API_KEY],
            base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        )
        self.open_meteo_client = OpenMeteoApiClient()
        self._tick = 0
        self._site_turbines: list[dict] = []
        self._turbine_generation: dict[str, dict] = {}
        self._wind_speed_today: float | None = None
        self._open_meteo_forecast: dict = {}
        # Last known-good current payloads per scope, kept so a failed fast-path
        # refresh keeps showing old data (marked stale) instead of blanking.
        self._last_current: dict[str, dict] = {}
        self._current_stale: dict[str, bool] = {scope: False for scope in SCOPES}
        # Last known-good summaries/windows per (scope, timeframe), kept so a
        # failed refresh keeps showing old data (marked stale) instead of blanking.
        self._last_summaries: dict[str, dict[str, dict]] = {scope: {} for scope in SCOPES}
        self._last_windows: dict[str, dict[str, dict]] = {scope: {} for scope in SCOPES}
        # Backoff retry state: consecutive failure count and the tick at which a
        # (scope, timeframe) should be retried again after a failure.
        self._summary_failures: dict[tuple[str, str], int] = {}
        self._summary_retry_at: dict[tuple[str, str], int] = {}
        self._summary_stale: dict[str, dict[str, bool]] = {
            scope: {} for scope in SCOPES
        }

    def apply_options(self) -> None:
        """Re-apply scan interval when options change."""
        scan_interval = self.entry.options.get(
            CONF_SCAN_INTERVAL,
            self.entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        self.update_interval = timedelta(seconds=scan_interval)

    async def _async_update_data(self) -> dict:
        """Fetch current owner/site data, turbine coordinates, and range summaries."""
        self._tick += 1
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
            self._fetch_timeframe_summaries(session, self._tick),
            return_exceptions=True,
        )
        owner_data = self._resolve_current_result(SCOPE_OWNER, owner_result)
        site_data = self._resolve_current_result(SCOPE_SITE, site_result)
        if isinstance(timeframe_result, BaseException):
            # Only an unexpected error can escape _fetch_timeframe_summaries;
            # per-timeframe API failures are absorbed inside it.
            raise timeframe_result
        timeframe_summaries, timeframe_windows = timeframe_result

        # Medium tier: turbines + today's wind-speed series (every 10 ticks)
        if self._tick == 1 or self._tick % 10 == 0:
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
                self._wind_speed_today = await self._fetch_latest_wind_speed(session)
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

            # Slow tier: Open-Meteo forecast (every 60 ticks ~1 hour)
            if self._tick == 1 or self._tick % 60 == 0:
                self._open_meteo_forecast = await self._fetch_open_meteo_forecast(session, coordinates)

        return {
            SCOPE_OWNER: owner_data,
            SCOPE_SITE: site_data,
            "coordinates": self._last_coordinates(),
            "timeframe_summaries": timeframe_summaries,
            "timeframe_windows": timeframe_windows,
            "summary_stale": self._summary_stale,
            "current_stale": dict(self._current_stale),
            "turbine_generation": self._turbine_generation,
            "wind_speed_today": self._wind_speed_today,
            "open_meteo_forecast": self._open_meteo_forecast,
            "tick": self._tick,
            "summary_failures": {
                f"{scope}:{timeframe}": count
                for (scope, timeframe), count in self._summary_failures.items()
            },
            "summary_retry_at": {
                f"{scope}:{timeframe}": retry_at
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
        self, session: aiohttp.ClientSession, tick: int
    ) -> tuple[dict[str, dict[str, dict]], dict[str, dict[str, dict]]]:
        tasks: list[tuple[str, str, asyncio.Task]] = []

        # Determine which timeframes to fetch this tick. The slow tier normally
        # runs every 60 ticks (~1 hour); a timeframe that failed on a slow/last
        # tick gets retried on a backoff schedule instead of waiting for the
        # next hourly slot.
        timeframes: set[str] = set(FAST_TIMEFRAMES)
        if tick == 1 or tick % 60 == 0:
            timeframes.update(SLOW_TIMEFRAMES)
        for (scope, timeframe), retry_at in self._summary_retry_at.items():
            if tick >= retry_at:
                timeframes.add(timeframe)
        _LOGGER.debug("Tick %s: fetching summaries for timeframes=%s", tick, sorted(timeframes))

        for scope in SCOPES:
            for timeframe in sorted(timeframes):
                if timeframe == "year":
                    range_value = str(dt_util.now().year)
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

        summaries: dict[str, dict[str, dict]] = {
            scope: dict(self._last_summaries[scope]) for scope in SCOPES
        }
        windows: dict[str, dict[str, dict]] = {
            scope: dict(self._last_windows[scope]) for scope in SCOPES
        }
        for (scope, timeframe, _), payload in zip(tasks, results):
            key = (scope, timeframe)
            if isinstance(payload, BaseException):
                failures = self._summary_failures.get(key, 0) + 1
                self._summary_failures[key] = failures
                # Backoff: retry after 1, 2, 4, ... ticks, capped at the 60-tick
                # hourly slot so we never hammer the API during an outage.
                retry_at = tick + min(2 ** (failures - 1), 60)
                self._summary_retry_at[key] = retry_at
                self._summary_stale[scope][timeframe] = True
                _LOGGER.warning(
                    "Failed to fetch summary for scope=%s timeframe=%s: %s "
                    "(keeping last known data, marked stale; next retry tick %s)",
                    scope,
                    timeframe,
                    payload,
                    retry_at,
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

        return summaries, windows

    async def _fetch_latest_wind_speed(self, session: aiohttp.ClientSession) -> float | None:
        try:
            payload = await self.client.get_wind_speed(
                session,
                scope=SCOPE_SITE,
                range_value="today",
            )
        except KirkHillApiError as exc:
            _LOGGER.warning("Failed to fetch wind-speed series: %s", exc)
            return self._wind_speed_today
        series = payload.get("series", [])
        if not isinstance(series, list) or not series:
            return None

        latest = series[-1]
        if not isinstance(latest, dict):
            return None

        value = latest.get("wind_speed_mps")
        return value if isinstance(value, (int, float)) else None

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
