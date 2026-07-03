"""Coordinator for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KirkHillApiClient
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

    def apply_options(self) -> None:
        """Re-apply scan interval when options change."""
        scan_interval = self.entry.options.get(
            CONF_SCAN_INTERVAL,
            self.entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        self.update_interval = timedelta(seconds=scan_interval)

    async def _async_update_data(self) -> dict:
        """Fetch current owner/site data, turbine coordinates, and range summaries."""
        async with aiohttp.ClientSession() as session:
            try:
                owner_data, site_data, site_turbines, timeframe_summaries, wind_speed_today = await asyncio.gather(
                    self.client.get_current(session, SCOPE_OWNER),
                    self.client.get_current(session, SCOPE_SITE),
                    self.client.get_turbines(session, SCOPE_SITE),
                    self._fetch_timeframe_summaries(session),
                    self._fetch_latest_wind_speed(session),
                )
            except KirkHillApiError as exc:
                raise UpdateFailed(str(exc)) from exc

        coordinates: dict[str, dict[str, float | str | None]] = {}
        for row in site_turbines:
            turbine_id = row.get("id")
            coord = row.get("coordinates") or {}
            if turbine_id:
                coordinates[turbine_id] = {
                    "latitude": coord.get("latitude"),
                    "longitude": coord.get("longitude"),
                    "source": coord.get("source"),
                    "openstreetmap_node_id": coord.get("openstreetmap_node_id"),
                }

        return {
            SCOPE_OWNER: owner_data,
            SCOPE_SITE: site_data,
            "coordinates": coordinates,
            "timeframe_summaries": timeframe_summaries,
            "wind_speed_today": wind_speed_today,
        }

    async def _fetch_timeframe_summaries(
        self, session: aiohttp.ClientSession
    ) -> dict[str, dict[str, dict]]:
        tasks: list[tuple[str, str, asyncio.Task]] = []

        for scope in SCOPES:
            for timeframe in TIMEFRAME_ORDER:
                range_value = TIMEFRAME_TO_RANGE[timeframe]
                if timeframe == "year":
                    range_value = str(datetime.now().year)
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
        payload = await self.client.get_wind_speed(
            session,
            scope=SCOPE_SITE,
            range_value="today",
        )
        series = payload.get("series", [])
        if not isinstance(series, list) or not series:
            return None

        latest = series[-1]
        if not isinstance(latest, dict):
            return None

        value = latest.get("wind_speed_mps")
        return value if isinstance(value, (int, float)) else None
