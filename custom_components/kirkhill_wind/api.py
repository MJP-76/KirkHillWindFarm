"""HTTP client for the Kirk Hill Wind Farm API."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL, SCOPE_OWNER, SCOPE_SITE
from .exceptions import (
    KirkHillApiError,
    KirkHillAuthError,
    KirkHillConnectionError,
    KirkHillPermissionError,
)

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=20)


def describe_key(key: str) -> str:
    """Describe a key without revealing it: length and shape, never characters.

    This string ends up in a log line, an abort message and quite possibly a
    bug report to whoever runs the dashboard, so it must never carry any part
    of the key. The one exception is the literal ``kh_live_`` prefix, which the
    dashboard's own oauth.md publishes as public documentation.

    Worth having: a sign-in that fails with "the key is not valid" is
    undecidable between "the dashboard issued a key the API rejects" and "we
    sent the wrong bytes" -- length and format answer that in one line.
    """
    stripped = key.strip()
    if re.fullmatch(r"kh_live_[A-Za-z0-9_-]+", stripped):
        shape = "matches the kh_live_ API-key format"
    elif stripped.startswith("kh_live_"):
        shape = "starts with kh_live_ but contains other characters"
    else:
        shape = "does not start with kh_live_"
    whitespace = ""
    if key != stripped:
        whitespace = f", {len(key) - len(stripped)} whitespace character(s) at the edges"
    return f"{len(stripped)}-char value{whitespace}, {shape}"


async def _error_detail(resp: aiohttp.ClientResponse) -> str:
    """Extract the dashboard's own explanation from an error response.

    The body is read exactly once: ``resp.json()`` consumes it, and a failed
    decode would leave a follow-up ``resp.text()`` empty. Errors are usually
    ``{"message": "The API key is not valid."}``, but an HTML error page from
    the proxy in front of the API is still more useful than nothing.
    """
    try:
        raw = await resp.read()
    except Exception:  # noqa: BLE001 -- never let diagnosis break the failure
        return ""
    if not raw:
        return ""
    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return " ".join(text.split())[:300]
    if isinstance(payload, dict):
        for key in ("message", "error", "error_description", "detail"):
            value = payload.get(key)
            if value:
                return str(value)[:300]
    return " ".join(text.split())[:300]


class KirkHillApiClient:
    """Async HTTP client aligned with the Kirk Hill Wind Farm OpenAPI spec."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        # Whitespace makes the API answer "The API key is not valid." while
        # every other part of the request is correct -- cheaper to strip it
        # here than to spend a release diagnosing it later.
        self._api_key = api_key.strip()
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
        started = time.monotonic()
        _LOGGER.debug("Kirk Hill API GET %s params=%s", path, params)
        try:
            async with session.get(
                url, params=params, headers=self._headers, timeout=TIMEOUT
            ) as resp:
                if resp.status >= 400:
                    # Read the body *before* raising: the dashboard explains
                    # itself in {"message": ...} -- "which rejection was this?"
                    # is the entire point of these exceptions, and without it a
                    # 401 during sign-in says nothing more than "invalid key".
                    detail = await _error_detail(resp)
                else:
                    detail = ""
                if resp.status == 401:
                    raise KirkHillAuthError(
                        "Invalid or missing API key"
                        + (f": {detail}" if detail else "")
                    )
                if resp.status == 403:
                    # Classified before raise_for_status(): otherwise this
                    # lands in the ClientError branch below and a permission
                    # problem reports itself as a network failure forever.
                    raise KirkHillPermissionError(
                        f"403 Forbidden for {path} (params={params}): "
                        + (detail or "the key does not permit this data")
                        + ". It must allow both 'My share' and 'Whole wind farm'."
                    )
                if resp.status >= 400:
                    # Previously raise_for_status() -> aiohttp.ClientResponseError
                    # -> KirkHillConnectionError(str(exc)), which kept the status
                    # but dropped the body. Same exception type, both halves kept.
                    raise KirkHillConnectionError(
                        f"HTTP {resp.status} from {path} (params={params}): "
                        + (detail or "no detail returned")
                    )
                body = await resp.json()
                _LOGGER.debug(
                    "Kirk Hill API GET %s params=%s -> HTTP %s in %.2fs",
                    path,
                    params,
                    resp.status,
                    time.monotonic() - started,
                )
                return body
        except KirkHillAuthError:
            raise
        except aiohttp.ClientError as exc:
            _LOGGER.debug(
                "Kirk Hill API GET %s failed after %.2fs: %s",
                path,
                time.monotonic() - started,
                exc,
            )
            raise KirkHillConnectionError(str(exc)) from exc
        except asyncio.TimeoutError as exc:
            _LOGGER.debug(
                "Kirk Hill API GET %s timed out after %.2fs",
                path,
                time.monotonic() - started,
            )
            raise KirkHillConnectionError("Request timed out") from exc

    def _parse_data(self, body: Any) -> dict[str, Any]:
        """Return the response payload, raising a typed error on a malformed envelope.

        The server normally wraps results as ``{"data": {...}}``, but a 200-level
        error envelope (``{"error": ...}``) would otherwise surface as a raw
        ``KeyError`` and escape this client's exception hierarchy. Failing here
        keeps every payload-format issue a catchable ``KirkHillApiError``.

        The ``dict`` guarantee is part of this contract, not just the caller's
        problem. Every caller does ``payload.get(...)`` straight afterwards, so a
        ``{"data": []}`` response would otherwise raise a bare ``AttributeError``
        from inside the client — which the coordinator's stale-data and retry
        machinery does not recognise, and which ``get_turbines`` hits before its
        own ``isinstance`` guard. Callers may rely on a dict coming back.
        """
        if not isinstance(body, dict):
            raise KirkHillApiError("Malformed response from Kirk Hill API: expected an object")
        if "data" not in body:
            raise KirkHillApiError("Malformed response from Kirk Hill API: missing 'data' key")
        data = body["data"]
        if not isinstance(data, dict):
            raise KirkHillApiError(
                f"Malformed response from Kirk Hill API: 'data' must be an object, "
                f"got {type(data).__name__}"
            )
        return data

    async def get_current(
        self, session: aiohttp.ClientSession, scope: str = SCOPE_OWNER
    ) -> dict[str, Any]:
        """GET /api/v1/current?scope={scope}."""
        body = await self._get(session, "/api/v1/current", {"scope": scope})
        return self._parse_data(body)

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
        turbines = self._parse_data(body).get("turbines")
        if not isinstance(turbines, list):
            raise KirkHillApiError(
                "Malformed response from Kirk Hill API: missing 'turbines' list"
            )
        return turbines

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
        return self._parse_data(body)

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
        return self._parse_data(body)

    async def test(self, session: aiohttp.ClientSession) -> None:
        """Validate the key against every scope this integration reads.

        Probing only the default (owner) scope would wave a share-only key
        straight through setup and strand the site sensors until the next poll.
        The API exposes no permission field to inspect, so the only way to know
        what a key may read is to ask for both scopes.
        """
        await self.get_current(session, SCOPE_OWNER)
        await self.get_current(session, SCOPE_SITE)


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
