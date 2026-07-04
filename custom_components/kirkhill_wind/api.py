"""HTTP client for the Kirk Hill Wind Farm API."""
from __future__ import annotations

import asyncio
import math
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
        self, session: aiohttp.ClientSession, scope: str = SCOPE_OWNER
    ) -> list[dict[str, Any]]:
        """GET /api/v1/turbines?scope={scope}."""
        body = await self._get(session, "/api/v1/turbines", {"scope": scope})
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


class WindyApiClient:
    """Async HTTP client for Windy point-forecast data (forecasting only)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._base_url = "https://api.windy.com"

    async def get_point_forecast(
        self,
        session: aiohttp.ClientSession,
        latitude: float,
        longitude: float,
        model: str = "ecmwf",
    ) -> dict[str, Any]:
        """POST /api/point-forecast/v2 and return parsed wind forecast summary."""
        payload = {
            "lat": latitude,
            "lon": longitude,
            "model": model,
            "parameters": ["wind", "windGust"],
            "levels": ["surface"],
            "key": self._api_key,
        }
        try:
            async with session.post(
                f"{self._base_url}/api/point-forecast/v2",
                json=payload,
                timeout=TIMEOUT,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            ) as resp:
                if resp.status in {401, 403}:
                    raise KirkHillAuthError("Invalid or unauthorized Windy API key")
                resp.raise_for_status()
                body = await resp.json()
        except KirkHillAuthError:
            raise
        except aiohttp.ClientError as exc:
            raise KirkHillConnectionError(str(exc)) from exc
        except asyncio.TimeoutError as exc:
            raise KirkHillConnectionError("Windy request timed out") from exc

        return self._summarize_forecast(body, model=model)

    def _summarize_forecast(self, body: dict[str, Any], model: str) -> dict[str, Any]:
        """Build stable summary metrics from Windy API payload."""
        timestamps = body.get("ts")
        if not isinstance(timestamps, list) or not timestamps:
            return {}

        u_series = self._extract_series(body, "wind_u")
        v_series = self._extract_series(body, "wind_v")
        if not u_series or not v_series:
            return {}

        speeds: list[float] = []
        for u, v in zip(u_series, v_series):
            if isinstance(u, (int, float)) and isinstance(v, (int, float)):
                speeds.append(math.sqrt((float(u) ** 2) + (float(v) ** 2)))
            else:
                speeds.append(float("nan"))

        valid = [s for s in speeds if not math.isnan(s)]
        if not valid:
            return {}

        def _avg(first_n: int) -> float | None:
            subset = [s for s in speeds[:first_n] if not math.isnan(s)]
            if not subset:
                return None
            return round(sum(subset) / len(subset), 2)

        next_hour = speeds[0] if not math.isnan(speeds[0]) else None
        return {
            "provider": "windy",
            "model": model,
            "forecast_points": len(valid),
            "next_hour_wind_speed_mps": round(next_hour, 2) if isinstance(next_hour, float) else None,
            "next_3h_avg_wind_speed_mps": _avg(3),
            "next_24h_avg_wind_speed_mps": _avg(24),
        }

    @staticmethod
    def _extract_series(body: dict[str, Any], prefix: str) -> list[Any] | None:
        """Return first list value for keys matching prefix (e.g. wind_u-*)."""
        for key, value in body.items():
            if key.startswith(prefix) and isinstance(value, list):
                return value
        return None
