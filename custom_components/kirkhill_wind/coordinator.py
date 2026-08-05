"""Coordinator for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    TIMEFRAME_ORDER,
    TIMEFRAME_TO_RANGE,
)
from .exceptions import KirkHillApiError

_LOGGER = logging.getLogger(__name__)

# Tiered update intervals (in coordinator ticks; tick 1 primes everything)
# Fast: every poll - current power + today/yesterday summaries
# Medium: every 10 polls (~10 min) - turbines, wind-speed series, week/month summaries
# Slow: every 60 polls (~1 hour) - Open-Meteo forecast, ytd/year/alltime summaries
FAST_TIMEFRAMES = ("today", "yesterday")
MEDIUM_TIMEFRAMES = ("week", "month")
SLOW_TIMEFRAMES = ("ytd", "year", "alltime")

ALL_TIMEFRAMES = FAST_TIMEFRAMES + MEDIUM_TIMEFRAMES + SLOW_TIMEFRAMES


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
        async with aiohttp.ClientSession() as session:
            try:
                owner_data, site_data, timeframe_summaries = await asyncio.gather(
                    self.client.get_current(session, SCOPE_OWNER),
                    self.client.get_current(session, SCOPE_SITE),
                    self._fetch_timeframe_summaries(session, self._tick),
                )
            except KirkHillApiError as exc:
                raise UpdateFailed(str(exc)) from exc

            # Medium tier: turbines + today's wind-speed series (every 10 ticks)
            if self._tick == 1 or self._tick % 10 == 0:
                try:
                    today_turbines = await self.client.get_turbines(
                        session, SCOPE_SITE, range_value="today"
                    )
                    alltime_turbines = await self.client.get_turbines(
                        session, SCOPE_SITE, range_value="all"
                    )
                except KirkHillApiError as exc:
                    raise UpdateFailed(str(exc)) from exc
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
            "coordinates": coordinates,
            "timeframe_summaries": timeframe_summaries,
            "turbine_generation": self._turbine_generation,
            "wind_speed_today": self._wind_speed_today,
            "open_meteo_forecast": self._open_meteo_forecast,
        }

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
    ) -> dict[str, dict[str, dict]]:
        tasks: list[tuple[str, str, asyncio.Task]] = []

        # Determine which timeframes to fetch this tick
        if tick == 1 or tick % 60 == 0:
            # Slow tier: every 60 ticks (~1 hour at 60s interval)
            timeframes = ALL_TIMEFRAMES
        elif tick % 10 == 0:
            # Medium tier: every 10 ticks (~10 min)
            timeframes = FAST_TIMEFRAMES + MEDIUM_TIMEFRAMES
        else:
            # Fast tier: every tick
            timeframes = FAST_TIMEFRAMES

        for scope in SCOPES:
            for timeframe in timeframes:
                if timeframe == "year":
                    range_value = str(datetime.now().year)
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

        summaries: dict[str, dict[str, dict]] = {scope: {} for scope in SCOPES}
        for (scope, timeframe, _), payload in zip(tasks, results):
            if isinstance(payload, Exception):
                _LOGGER.warning(
                    "Failed to fetch summary for scope=%s timeframe=%s: %s",
                    scope,
                    timeframe,
                    payload,
                )
                summaries[scope][timeframe] = {}
                continue

            summary = payload.get("summary")
            summaries[scope][timeframe] = summary if isinstance(summary, dict) else {}

        return summaries

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
                return await self.open_meteo_client.get_point_forecast(
                    session,
                    latitude=latitude,
                    longitude=longitude,
                )

            except (aiohttp.ClientError, asyncio.TimeoutError, KirkHillApiError) as exc:
                last_exc = exc
                await asyncio.sleep(2 ** attempt)

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
