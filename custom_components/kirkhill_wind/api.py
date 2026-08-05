"""HTTP client for the Kirk Hill Wind Farm API."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL, SCOPE_OWNER
from .exceptions import KirkHillAuthError, KirkHillConnectionError

TIMEOUT = aiohttp.ClientTimeout(total=20)


class KirkHillApiClient:
    """Async HTTP client aligned with the Kirk Hill Wind Farm OpenAPI spec."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + self._api_key,
            "Accept": "application/json",
        }

    async def _get(
        self, session: aiohttp.ClientSession, path: str, params: dict[str, str]
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with session.get(
                url, params=params, headers=self._headers, timeout=TIMEOUT
            ) as resp:
                if resp.status == 401:
                    raise KirkHillAuthError("Invalid or missing API key")
                resp.raise_for_status()
                return await resp.json()
        except KirkHillAuthError:
            raise
        except aiohttp.ClientError as exc:
            raise KirkHillConnectionError(str(exc)) from exc
        except asyncio.TimeoutError as exc:
            raise KirkHillConnectionError("Request timed out") from exc

    async def get_current(
        self, session: aiohttp.ClientSession, scope: str = SCOPE_OWNER
    ) -> dict[str, Any]:
        """GET /api/v1/current?scope={scope}."""
        body = await self._get(session, "/api/v1/current", {"scope": scope})
        return body["data"]

    async def get_turbines(
        self,
        session: aiohttp.ClientSession,
        scope: str = SCOPE_OWNER,
        range_value: str = "7d",
    ) -> list[dict[str, Any]]:
        """GET /api/v1/turbines?scope={scope}&range={range_value}."""
        body = await self._get(
            session,
            "/api/v1/turbines",
            {"scope": scope, "range": range_value},
        )
        return body["data"]["turbines"]

    async def get_summary(
        self,
        session: aiohttp.ClientSession,
        scope: str = SCOPE_OWNER,
        range_value: str = "today",
    ) -> dict[str, Any]:
        """GET /api/v1/summary?scope={scope}&range={range_value}."""
        body = await self._get(
            session,
            "/api/v1/summary",
            {"scope": scope, "range": range_value},
        )
        return body["data"]

    async def get_wind_speed(
        self,
        session: aiohttp.ClientSession,
        scope: str = SCOPE_OWNER,
        range_value: str = "today",
    ) -> dict[str, Any]:
        """GET /api/v1/wind-speed?scope={scope}&range={range_value}."""
        body = await self._get(
            session,
            "/api/v1/wind-speed",
            {"scope": scope, "range": range_value},
        )
        return body["data"]

    async def test(self, session: aiohttp.ClientSession) -> None:
        """Validate the API key by making a minimal current request."""
        await self.get_current(session, SCOPE_OWNER)


class OpenMeteoApiClient:
    """Async HTTP client for Open-Meteo wind forecast data (forecasting only)."""

    def __init__(self) -> None:
        self._base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_point_forecast(
        self,
        session: aiohttp.ClientSession,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """GET Open-Meteo forecast and return parsed wind forecast summary."""
        params = {
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "hourly": "wind_speed_10m",
            "forecast_days": "2",
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
        try:
            async with session.get(
                self._base_url,
                params=params,
                timeout=TIMEOUT,
                headers={"Accept": "application/json"},
            ) as resp:
                resp.raise_for_status()
                body = await resp.json()
        except aiohttp.ClientError as exc:
            raise KirkHillConnectionError(str(exc)) from exc
        except asyncio.TimeoutError as exc:
            raise KirkHillConnectionError("Open-Meteo request timed out") from exc

        return self._summarize_forecast(body)

    def _summarize_forecast(self, body: dict[str, Any]) -> dict[str, Any]:
        """Build stable summary metrics from Open-Meteo payload."""
        hourly = body.get("hourly")
        if not isinstance(hourly, dict):
            return {}

        timestamps = hourly.get("time")
        speeds = hourly.get("wind_speed_10m")
        if not isinstance(timestamps, list) or not isinstance(speeds, list):
            return {}

        points: list[tuple[datetime, float]] = []
        for time_raw, speed_raw in zip(timestamps, speeds):
            point_time = self._parse_hourly_timestamp(time_raw)
            if point_time is None or not isinstance(speed_raw, (int, float)):
                continue
            points.append((point_time, float(speed_raw)))

        if not points:
            return {}

        now_utc = datetime.now(timezone.utc)
        future_speeds = [speed for point_time, speed in points if point_time > now_utc]
        if not future_speeds:
            future_speeds = [speed for _, speed in points]

        if not future_speeds:
            return {}

        def _avg(first_n: int) -> float | None:
            subset = future_speeds[:first_n]
            if not subset:
                return None
            return round(sum(subset) / len(subset), 2)

        return {
            "provider": "open_meteo",
            "model": "open-meteo",
            "forecast_points": len(future_speeds),
            "next_hour_wind_speed_mps": round(future_speeds[0], 2),
            "next_3h_avg_wind_speed_mps": _avg(3),
            "next_24h_avg_wind_speed_mps": _avg(24),
        }

    @staticmethod
    def _parse_hourly_timestamp(raw: Any) -> datetime | None:
        """Parse Open-Meteo hourly timestamp as UTC."""
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
