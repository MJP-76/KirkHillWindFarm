"""HTTP client for the Kirk Hill Wind Farm API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
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
        whitespace = (
            f", {len(key) - len(stripped)} whitespace character(s) at the edges"
        )
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
                        "Invalid or missing API key" + (f": {detail}" if detail else "")
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
            raise KirkHillApiError(
                "Malformed response from Kirk Hill API: expected an object"
            )
        if "data" not in body:
            raise KirkHillApiError(
                "Malformed response from Kirk Hill API: missing 'data' key"
            )
        data = body["data"]
        if not isinstance(data, dict):
            raise KirkHillApiError(
                f"Malformed response from Kirk Hill API: 'data' must be an object, got {type(data).__name__}"
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
        # docs/api.md: the spec advertises the full Range set for this
        # endpoint, but only today and all are known to be served, so the
        # default must not be one of the values that 422s.
        range_value: str = "today",
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
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/summary?scope={scope}&range={range_value}[&from&to].

        ``from_ts``/``to_ts`` (ISO-8601) are required by the API when
        ``range_value == "custom"`` — the spec's first-class window, used for
        the rolling last-12-months timeframe. Named ranges never send them.
        """
        params: dict[str, str] = {"scope": scope, "range": range_value}
        if from_ts is not None:
            params["from"] = from_ts
        if to_ts is not None:
            params["to"] = to_ts
        body = await self._get(
            session,
            "/api/v1/summary",
            params,
        )
        return self._parse_data(body)

    async def get_forecast(
        self, session: aiohttp.ClientSession, scope: str = SCOPE_OWNER
    ) -> dict[str, Any]:
        """GET /api/v1/forecast?scope={scope}.

        The wind farm's own forecast: its weather models run at hub height
        (80 or 100 m, per the spec) against its own turbines, so this replaces
        both the 10 m Open-Meteo reading we used to ask for and the coordinate
        centroid we used to derive it from. The payload also carries a
        generation forecast, which a wind-only source cannot produce.
        """
        body = await self._get(session, "/api/v1/forecast", {"scope": scope})
        return self._parse_data(body)

    async def get_benchmarks(
        self,
        session: aiohttp.ClientSession,
        scope: str = SCOPE_OWNER,
        range_value: str = "today",
    ) -> dict[str, Any]:
        """GET /api/v1/benchmarks?scope={scope}&range={range_value}.

        Long-term expectations (P50/P75/P90) for a window, plus how the
        actual generation for that window measures against them. The spec is
        explicit that these are **not** weather forecasts: they are
        ``long_term_monthly_budgets``.
        """
        body = await self._get(
            session,
            "/api/v1/benchmarks",
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


def _parse_timestamp(raw: Any) -> datetime | None:
    """Parse an API timestamp to aware UTC, or None if it is not one."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # A naive payload timestamp is read as UTC rather than rejected: an
    # unrecognised offset would otherwise drop every point and make a valid
    # forecast look empty.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def summarize_forecast(data: Any, now: datetime | None = None) -> dict[str, Any]:
    """Build stable summary metrics from the ``/api/v1/forecast`` payload.

    Averages are taken over a *time window* rather than over a fixed number of
    points, so they stay correct whatever interval the API chooses to publish
    (hourly today, 15-minute tomorrow): the next hour is every point that
    overlaps ``[now, now + 1h)``, not "the first three points".

    Returns ``{}`` when the payload holds no point reaching into the future.
    That is the contract the coordinator's "drop to no-forecast" path depends
    on -- a payload this cannot read must yield nothing rather than raise,
    because a forecast must never fail the core update.
    """
    if not isinstance(data, dict):
        return {}
    days = data.get("days")
    if not isinstance(days, list):
        return {}

    reference = now or datetime.now(timezone.utc)

    points: list[tuple[datetime, datetime, float]] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        raw_points = day.get("points")
        if not isinstance(raw_points, list):
            continue
        for point in raw_points:
            if not isinstance(point, dict):
                continue
            start = _parse_timestamp(point.get("from"))
            end = _parse_timestamp(point.get("to"))
            speed = point.get("wind_speed_mps")
            if (
                start is None
                or end is None
                or isinstance(speed, bool)
                or not isinstance(speed, (int, float))
            ):
                continue
            points.append((start, end, float(speed)))

    # A forecast entirely in the past is not a forecast: the upstream run is
    # late or stale, and reporting a number would put a lie on the graph.
    if not points or not any(end > reference for _, end, _ in points):
        return {}

    def _average(hours: float) -> float | None:
        horizon = reference + timedelta(hours=hours)
        window = [
            speed for start, end, speed in points if end > reference and start < horizon
        ]
        return round(sum(window) / len(window), 2) if window else None

    future_points = sum(1 for _, end, _ in points if end > reference)
    return {
        "status": data.get("status"),
        "scope": data.get("scope"),
        "generated_at": data.get("generated_at"),
        "model_version": data.get("model_version"),
        "weather_stale": data.get("weather_stale"),
        "operational_stale": data.get("operational_stale"),
        "forecast_points": future_points,
        "next_hour_wind_speed_mps": _average(1),
        "next_3h_avg_wind_speed_mps": _average(3),
        "next_24h_avg_wind_speed_mps": _average(24),
    }


def _number(value: Any) -> float | None:
    """Coerce a numeric field to float, or None when it is absent/null/garbage."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _total(values: list[float | None]) -> float | None:
    """Sum a window's per-month figures, or None if any part is unknown.

    A partial sum would read as a real total and be quietly wrong, so an
    unknown part makes the whole window unknown.
    """
    if not values or any(value is None for value in values):
        return None
    return round(sum(values), 3)


def summarize_benchmarks(data: Any) -> dict[str, Any]:
    """Reduce the ``/api/v1/benchmarks`` payload to one window's figures.

    The payload reports one entry per calendar month the window touches, each
    carrying its own targets, so a window spanning two months -- any rolling
    30 days does -- has to be summed rather than read off the first entry.
    Percentages are the exception: they cannot be summed, so
    ``vs_p50_percent`` is derived from the summed energies instead of
    averaged across months.

    Returns ``{}`` when the payload holds nothing usable. That is the
    contract the coordinator's "drop to no benchmarks" path depends on: a
    payload this cannot read must yield nothing rather than raise, because
    side data must never fail the core update.
    """
    if not isinstance(data, dict):
        return {}
    months = data.get("months")
    if not isinstance(months, list) or not months:
        return {}

    target_totals: dict[str, list[float | None]] = {"p50": [], "p75": [], "p90": []}
    actuals: list[float | None] = []
    data_complete = True

    for month in months:
        if not isinstance(month, dict):
            return {}
        targets = month.get("targets")
        if not isinstance(targets, dict):
            return {}
        # Present-but-null is a legitimate value (the schema allows it) and
        # becomes an unknown total; absent is a malformed payload, which must
        # yield nothing rather than a window of invented nulls.
        if "generation_kwh" not in month or "generation_complete" not in month:
            return {}
        for percentile in target_totals:
            target = targets.get(percentile)
            if not isinstance(target, dict) or "period_kwh" not in target:
                return {}
            target_totals[percentile].append(_number(target.get("period_kwh")))
        actuals.append(_number(month.get("generation_kwh")))
        if month.get("generation_complete") is False:
            data_complete = False

    p50 = _total(target_totals["p50"])
    p75 = _total(target_totals["p75"])
    p90 = _total(target_totals["p90"])
    actual = _total(actuals)
    vs_p50 = round(actual / p50 * 100, 2) if (actual is not None and p50) else None

    return {
        "basis": data.get("basis"),
        "timezone": data.get("timezone"),
        "month_count": len(months),
        "actual_kwh": actual,
        "p50_kwh": p50,
        "p75_kwh": p75,
        "p90_kwh": p90,
        "vs_p50_percent": vs_p50,
        "data_complete": data_complete,
    }
