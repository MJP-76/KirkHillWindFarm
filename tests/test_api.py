"""Tests for the API client — exception hierarchy and response parsing."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.kirkhill_wind.api import (
    KirkHillApiClient,
    describe_key,
    summarize_benchmarks,
    summarize_forecast,
)
from custom_components.kirkhill_wind.const import SCOPE_OWNER, SCOPE_SITE
from custom_components.kirkhill_wind.exceptions import (
    KirkHillApiError,
    KirkHillAuthError,
    KirkHillConnectionError,
    KirkHillPermissionError,
)


class TestExceptionHierarchy:
    """Verify the exception classes have the right inheritance."""

    def test_auth_is_api_error(self):
        assert issubclass(KirkHillAuthError, KirkHillApiError)

    def test_connection_is_api_error(self):
        assert issubclass(KirkHillConnectionError, KirkHillApiError)

    def test_all_catchable_as_api_error(self):
        """All KirkHill exceptions should be catchable as KirkHillApiError."""
        with pytest.raises(KirkHillApiError):
            raise KirkHillAuthError("test")
        with pytest.raises(KirkHillApiError):
            raise KirkHillConnectionError("test")


class TestApiClient:
    """Verify the API client handles responses correctly."""

    def test_parse_data_valid(self):
        client = KirkHillApiClient(api_key="key")
        result = client._parse_data({"data": {"power": 100}})
        assert result == {"power": 100}

    def test_parse_data_missing_key_raises(self):
        client = KirkHillApiClient(api_key="key")
        with pytest.raises(KirkHillApiError, match="missing 'data' key"):
            client._parse_data({"error": "bad request"})

    def test_parse_data_non_dict_raises(self):
        client = KirkHillApiClient(api_key="key")
        with pytest.raises(KirkHillApiError, match="expected an object"):
            client._parse_data("not a dict")

    def test_parse_data_list_raises(self):
        client = KirkHillApiClient(api_key="key")
        with pytest.raises(KirkHillApiError, match="expected an object"):
            client._parse_data([1, 2, 3])

    # -- The dict guarantee -------------------------------------------------
    # Every caller does payload.get(...) straight after _parse_data, so a
    # {"data": []} response would otherwise raise a bare AttributeError from
    # inside the client -- not a KirkHillApiError -- and the coordinator's
    # stale-data and retry-backoff machinery would never engage.

    @pytest.mark.parametrize(
        "data",
        [[], ["a"], 0, 1, 3.5, True, "text", None],
        ids=["empty-list", "list", "int-0", "int", "float", "bool", "str", "none"],
    )
    def test_parse_data_non_object_payload_raises(self, data):
        """A non-object 'data' must raise KirkHillApiError, not leak a type error."""
        client = KirkHillApiClient(api_key="key")
        with pytest.raises(KirkHillApiError, match="must be an object"):
            client._parse_data({"data": data})

    def test_parse_data_reports_the_offending_type(self):
        """The error names the type it got, so a bad envelope is diagnosable."""
        client = KirkHillApiClient(api_key="key")
        with pytest.raises(KirkHillApiError, match="got list"):
            client._parse_data({"data": []})

    def test_parse_data_unwraps_envelope_and_returns_data(self):
        """A valid payload passes through unchanged, envelope discarded."""
        client = KirkHillApiClient(api_key="key")
        payload = {"summary": {"total_power_kw": 1.0}, "window": {"from": "x"}}
        result = client._parse_data({"data": payload, "meta": {"ignored": True}})
        assert result == payload
        assert "meta" not in result

    @pytest.mark.asyncio
    async def test_get_current_rejects_non_object_data(self):
        """A 200 response carrying a list payload surfaces as KirkHillApiError.

        Regression guard for the coordinator path: without the guarantee this
        escaped as AttributeError inside the client.
        """
        client = KirkHillApiClient(api_key="key")
        session = MagicMock()
        body = {"data": []}

        async def fake_get(session, path, params):
            return body

        with patch.object(client, "_get", side_effect=fake_get):
            with pytest.raises(KirkHillApiError, match="must be an object"):
                await client.get_current(session, SCOPE_OWNER)

    @pytest.mark.asyncio
    async def test_get_summary_sends_from_and_to_only_when_provided(self):
        """range=custom requires from/to; named ranges must never send them."""
        client = KirkHillApiClient(api_key="key")
        session = MagicMock()
        captured: list[dict] = []

        async def fake_get(session, path, params):
            captured.append(params)
            return {"data": {"total_generation_kwh": 1.0}}

        with patch.object(client, "_get", side_effect=fake_get):
            await client.get_summary(
                session,
                SCOPE_OWNER,
                "custom",
                from_ts="2025-10-23T12:00:00Z",
                to_ts="2026-10-23T12:00:00Z",
            )
            await client.get_summary(session, SCOPE_OWNER, "ytd")

        rolling, named = captured
        assert rolling == {
            "scope": SCOPE_OWNER,
            "range": "custom",
            "from": "2025-10-23T12:00:00Z",
            "to": "2026-10-23T12:00:00Z",
        }
        assert named == {"scope": SCOPE_OWNER, "range": "ytd"}

    @pytest.mark.asyncio
    async def test_get_turbines_rejects_non_object_data(self):
        """get_turbines previously hit .get() before its own isinstance guard."""
        client = KirkHillApiClient(api_key="key")
        session = MagicMock()

        async def fake_get(session, path, params):
            return {"data": []}

        with patch.object(client, "_get", side_effect=fake_get):
            with pytest.raises(KirkHillApiError, match="must be an object"):
                await client.get_turbines(session, SCOPE_SITE, range_value="today")

    @pytest.mark.asyncio
    async def test_get_turbines_rejects_object_without_turbines(self):
        """A valid envelope missing the 'turbines' list still raises."""
        client = KirkHillApiClient(api_key="key")
        session = MagicMock()

        async def fake_get(session, path, params):
            return {"data": {"summary": {}}}

        with patch.object(client, "_get", side_effect=fake_get):
            with pytest.raises(KirkHillApiError, match="missing 'turbines' list"):
                await client.get_turbines(session, SCOPE_SITE, range_value="today")


class TestForecastSummarize:
    """Verify the wind farm's own forecast summarization."""

    NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    @staticmethod
    def _payload(points, **extra):
        data = {
            "status": "ready",
            "scope": "owner",
            "days": [{"key": "today", "points": points}],
        }
        data.update(extra)
        return data

    @staticmethod
    def _point(start: str, end: str, speed) -> dict:
        return {
            "from": start,
            "to": end,
            "power_kw": 100.0,
            "wind_speed_mps": speed,
            "nowcast": False,
        }

    def test_hourly_points_are_averaged_over_the_window(self):
        points = [
            self._point(f"2026-11-03T{h}:00:00+00:00", f"2026-11-03T{h + 1}:00:00+00:00", float(s))
            for h, s in ((12, 4), (13, 6), (14, 8), (15, 10))
        ]
        result = summarize_forecast(self._payload(points), now=self.NOW)

        # The next hour is 12:00-13:00 alone, whatever comes after it.
        assert result["next_hour_wind_speed_mps"] == 4.0
        # The next three hours are 12, 13 and 14.
        assert result["next_3h_avg_wind_speed_mps"] == 6.0
        assert result["forecast_points"] == 4

    def test_the_window_is_time_based_not_count_based(self):
        """Fifteen-minute points must not be averaged as if they were hours.

        A fixed "first N points" rule silently turns a 15-minute forecast's
        next hour into the next fifteen minutes.
        """
        points = []
        for m, s in ((0, 4), (15, 6), (30, 8), (45, 10)):
            start = datetime(2026, 11, 3, 12, m, tzinfo=timezone.utc)
            end = start + timedelta(minutes=15)
            points.append(self._point(start.isoformat(), end.isoformat(), float(s)))
        result = summarize_forecast(self._payload(points), now=self.NOW)

        assert result["next_hour_wind_speed_mps"] == 7.0

    def test_the_twenty_four_hour_average_covers_what_exists(self):
        points = [
            self._point("2026-11-03T12:00:00+00:00", "2026-11-03T13:00:00+00:00", 5.0),
            self._point("2026-11-03T13:00:00+00:00", "2026-11-03T14:00:00+00:00", 7.0),
        ]
        result = summarize_forecast(self._payload(points), now=self.NOW)

        assert result["next_24h_avg_wind_speed_mps"] == 6.0

    def test_a_forecast_entirely_in_the_past_yields_nothing(self):
        """A late upstream run must not put a stale number on the graph."""
        points = [self._point("2026-11-03T08:00:00+00:00", "2026-11-03T09:00:00+00:00", 5.0)]
        assert summarize_forecast(self._payload(points), now=self.NOW) == {}

    def test_status_and_staleness_are_carried_through(self):
        points = [self._point("2026-11-03T12:00:00+00:00", "2026-11-03T13:00:00+00:00", 5.0)]
        result = summarize_forecast(
            self._payload(points, status="stale", weather_stale=True, model_version="v3"),
            now=self.NOW,
        )

        assert result["status"] == "stale"
        assert result["weather_stale"] is True
        assert result["model_version"] == "v3"

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"days": []},
            {"days": "not-a-list"},
            {"days": [{"points": "not-a-list"}]},
            {"days": [{"points": [None, 42, "junk"]}]},
            {"days": [{"points": [{"from": "junk", "to": "junk", "wind_speed_mps": 5.0}]}]},
        ],
    )
    def test_a_payload_it_cannot_read_yields_nothing(self, body):
        """The coordinator's "drop to no-forecast" path depends on this."""
        assert summarize_forecast(body, now=self.NOW) == {}

    def test_null_wind_speeds_are_skipped_not_averaged(self):
        points = [
            self._point("2026-11-03T12:00:00+00:00", "2026-11-03T13:00:00+00:00", 6.0),
            self._point("2026-11-03T13:00:00+00:00", "2026-11-03T14:00:00+00:00", None),
        ]
        result = summarize_forecast(self._payload(points), now=self.NOW)

        assert result["next_hour_wind_speed_mps"] == 6.0
        assert result["next_3h_avg_wind_speed_mps"] == 6.0

    @staticmethod
    def _day(key, energy, *, complete=True, forecast_from="2026-11-03T12:00:00+00:00"):
        return {
            "key": key,
            "date": "2026-11-03",
            "from": "2026-11-03T00:00:00+00:00",
            "to": "2026-11-04T00:00:00+00:00",
            "forecast_from": forecast_from,
            "complete": complete,
            "energy_kwh": energy,
            "points": [
                {
                    "from": "2026-11-03T12:00:00+00:00",
                    "to": "2026-11-03T13:00:00+00:00",
                    "power_kw": 100.0,
                    "wind_speed_mps": 6.0,
                    "nowcast": False,
                }
            ],
        }

    @staticmethod
    def _days_payload(days):
        return {"status": "ready", "scope": "owner", "days": days}

    def test_daily_energy_totals_are_carried_through(self):
        payload = self._days_payload([self._day("today", 812.5), self._day("tomorrow", 1904.0)])
        result = summarize_forecast(payload, now=self.NOW)

        assert result["days"]["today"]["energy_kwh"] == 812.5
        assert result["days"]["tomorrow"]["energy_kwh"] == 1904.0
        assert result["days"]["today"]["complete"] is True
        # The wind figures ride along in the same payload.
        assert result["next_hour_wind_speed_mps"] == 6.0

    def test_today_starts_mid_day_not_at_midnight(self):
        """The spec: today's total covers only the remaining time."""
        payload = self._days_payload([self._day("today", 812.5, forecast_from="2026-11-03T15:00:00+00:00")])
        result = summarize_forecast(payload, now=self.NOW)

        assert result["days"]["today"]["forecast_from"] == "2026-11-03T15:00:00+00:00"

    def test_an_absent_energy_is_unknown_not_zero(self):
        """Zero would read as a calm day rather than missing data."""
        payload = self._days_payload([self._day("today", None)])
        result = summarize_forecast(payload, now=self.NOW)

        assert result["days"]["today"]["energy_kwh"] is None

    @pytest.mark.parametrize("key", ["yesterday", "next_week", None, 3])
    def test_an_unrecognised_day_key_is_dropped(self, key):
        payload = self._days_payload([self._day(key, 100.0), self._day("today", 812.5)])
        result = summarize_forecast(payload, now=self.NOW)

        assert set(result["days"]) == {"today"}

    def test_a_non_boolean_complete_reads_as_unknown(self):
        payload = self._days_payload([self._day("today", 812.5, complete="yes")])
        result = summarize_forecast(payload, now=self.NOW)

        assert result["days"]["today"]["complete"] is None

    def test_a_day_entry_that_is_not_an_object_is_skipped(self):
        payload = self._days_payload(["junk", self._day("today", 812.5)])
        result = summarize_forecast(payload, now=self.NOW)

        assert set(result["days"]) == {"today"}


class TestSummarizeBenchmarks:
    """Verify the P50/P75/P90 window reduction."""

    @staticmethod
    def _target(period_kwh, *, vs=None):
        return {
            "period_kwh": period_kwh,
            "full_month_kwh": 1000.0,
            "expected_capacity_factor_percent": 31.5,
            "vs_period_percent": vs,
            "full_month_achieved_percent": None,
        }

    @classmethod
    def _month(cls, generation, p50, p75, p90, *, month="2026-11", complete=True):
        return {
            "month": month,
            "from": "2026-11-01T00:00:00+00:00",
            "to": "2026-12-01T00:00:00+00:00",
            "hours": 720.0,
            "full_month_hours": 720.0,
            "generation_kwh": generation,
            "generation_complete": complete,
            "boundary_complete": False,
            "is_full_month": False,
            "targets": {
                "p50": cls._target(p50),
                "p75": cls._target(p75),
                "p90": cls._target(p90),
            },
        }

    @staticmethod
    def _payload(months, **extra):
        data = {
            "basis": "long_term_monthly_budgets",
            "timezone": "Europe/London",
            "months": months,
        }
        data.update(extra)
        return data

    def test_a_single_month_reads_straight_off_it(self):
        result = summarize_benchmarks(self._payload([self._month(80.0, 100.0, 120.0, 140.0)]))

        assert result["p50_kwh"] == 100.0
        assert result["p75_kwh"] == 120.0
        assert result["p90_kwh"] == 140.0
        assert result["actual_kwh"] == 80.0
        # 80 of an expected 100.
        assert result["vs_p50_percent"] == 80.0
        assert result["month_count"] == 1
        assert result["basis"] == "long_term_monthly_budgets"
        assert result["timezone"] == "Europe/London"
        assert result["data_complete"] is True

    def test_a_window_spanning_two_months_is_summed_not_read_off_the_first(self):
        """Any rolling 30 days crosses a calendar month boundary."""
        months = [
            self._month(40.0, 50.0, 60.0, 70.0, month="2026-10"),
            self._month(60.0, 150.0, 180.0, 210.0, month="2026-11"),
        ]
        result = summarize_benchmarks(self._payload(months))

        assert result["p50_kwh"] == 200.0
        assert result["actual_kwh"] == 100.0
        assert result["month_count"] == 2

    def test_the_percentage_is_derived_from_energy_not_averaged(self):
        """Averaging 80% and 40% would say 60%; the window is 100 of 200."""
        months = [
            self._month(40.0, 50.0, 60.0, 70.0, month="2026-10"),
            self._month(60.0, 150.0, 180.0, 210.0, month="2026-11"),
        ]
        result = summarize_benchmarks(self._payload(months))

        assert result["vs_p50_percent"] == 50.0

    def test_an_unknown_actual_blanks_the_percentage_but_keeps_the_targets(self):
        months = [self._month(None, 100.0, 120.0, 140.0)]
        result = summarize_benchmarks(self._payload(months))

        assert result["actual_kwh"] is None
        assert result["vs_p50_percent"] is None
        assert result["p50_kwh"] == 100.0

    def test_an_unknown_target_blanks_the_whole_window(self):
        """A partial sum would read as a real total and be quietly wrong."""
        months = [
            self._month(40.0, 50.0, 60.0, 70.0, month="2026-10"),
            self._month(60.0, None, 180.0, 210.0, month="2026-11"),
        ]
        result = summarize_benchmarks(self._payload(months))

        assert result["p50_kwh"] is None
        assert result["p75_kwh"] == 240.0
        assert result["vs_p50_percent"] is None

    def test_incomplete_generation_is_reported_not_hidden(self):
        """The spec says check completeness before comparing totals."""
        result = summarize_benchmarks(self._payload([self._month(80.0, 100.0, 120.0, 140.0, complete=False)]))

        assert result["data_complete"] is False

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"months": []},
            {"months": "not-a-list"},
            {"months": [None]},
            {"months": [{"targets": "not-a-object"}]},
            {"months": [{"targets": {"p50": {}, "p75": {}, "p90": {}}}]},
            {"months": [{"generation_kwh": 1.0}]},
            "junk",
            None,
            42,
        ],
    )
    def test_a_payload_it_cannot_read_yields_nothing(self, body):
        """The coordinator's "drop to no benchmarks" path depends on this."""
        assert summarize_benchmarks(body) == {}


class TestPermissionHandling:
    """403 must mean "reads less than we need", not "can't connect"."""

    class _Response:
        """Minimal aiohttp response: only the status is under test."""

        def __init__(self, status: int) -> None:
            self.status = status

        async def json(self) -> dict:
            return {"data": {}}

        def raise_for_status(self) -> None:
            raise AssertionError(
                "401/403 must be classified before raise_for_status(); reaching "
                "it means a permission failure became a connection error"
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info) -> bool:
            return False

    class _Session:
        def __init__(self, status: int) -> None:
            self._status = status

        def get(self, url: str, **kwargs) -> "TestPermissionHandling._Response":
            return TestPermissionHandling._Response(self._status)

    @pytest.mark.asyncio
    async def test_403_raises_a_permission_error(self):
        client = KirkHillApiClient(api_key="key")

        with pytest.raises(KirkHillPermissionError, match="403"):
            await client._get(self._Session(403), "/api/v1/current", {"scope": "site"})

    @pytest.mark.asyncio
    async def test_401_is_still_the_only_reauth_trigger(self):
        client = KirkHillApiClient(api_key="key")

        with pytest.raises(KirkHillAuthError):
            await client._get(self._Session(401), "/api/v1/current", {"scope": "owner"})

        assert issubclass(KirkHillPermissionError, KirkHillApiError)
        assert not issubclass(KirkHillPermissionError, KirkHillAuthError), (
            "A 403 must not start re-auth: re-entering the same narrow key would fail the same way."
        )

    @pytest.mark.asyncio
    async def test_validation_asks_for_every_scope_the_integration_reads(self):
        client = KirkHillApiClient(api_key="key")
        seen: list[str] = []

        async def fake_get(session, path, params):
            seen.append(params["scope"])
            return {"data": {}}

        with patch.object(client, "_get", side_effect=fake_get):
            await client.test(object())

        assert seen == [SCOPE_OWNER, SCOPE_SITE], (
            "An owner-only probe waves a share-only key through setup and "
            "strands the site sensors on the very next poll."
        )

    @pytest.mark.asyncio
    async def test_a_share_only_key_fails_validation(self):
        client = KirkHillApiClient(api_key="key")

        async def fake_get(session, path, params):
            if params.get("scope") == SCOPE_SITE:
                raise KirkHillPermissionError("403 for scope=site")
            return {"data": {}}

        with patch.object(client, "_get", side_effect=fake_get):
            with pytest.raises(KirkHillPermissionError):
                await client.test(object())


class TestValidationDiagnostics:
    """The failure must carry the dashboard's own words, not just a status.

    A sign-in that dies with "the key could not be used" and no reason is
    undiagnosable: 401, 429 and a timeout all looked identical. These pin the
    reason to the exception, which config_flow logs and quotes.
    """

    class _ErrorResponse:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        async def read(self) -> bytes:
            return self._body

        async def json(self):
            raise AssertionError("error bodies are read once, via read()")

        def raise_for_status(self) -> None:
            raise AssertionError("statuses are classified explicitly, not via raise_for_status")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info) -> bool:
            return False

    class _Session:
        def __init__(self, status: int, body: bytes) -> None:
            self._status = status
            self._body = body

        def get(self, url: str, **kwargs) -> "TestValidationDiagnostics._ErrorResponse":
            return TestValidationDiagnostics._ErrorResponse(self._status, self._body)

    @pytest.mark.asyncio
    async def test_401_quotes_the_dashboard_message(self):
        client = KirkHillApiClient(api_key="key")
        body = b'{"message": "The API key is not valid."}'

        with pytest.raises(KirkHillAuthError, match="The API key is not valid"):
            await client._get(self._Session(401, body), "/api/v1/current", {"scope": "owner"})

    @pytest.mark.asyncio
    async def test_401_without_json_still_reports_something(self):
        """A proxy error page is still better than a bare "invalid key"."""
        client = KirkHillApiClient(api_key="key")

        with pytest.raises(KirkHillAuthError, match="Bad Gateway"):
            await client._get(
                self._Session(401, b"<html><body>Bad Gateway</body></html>"),
                "/api/v1/current",
                {"scope": "owner"},
            )

    @pytest.mark.asyncio
    async def test_other_http_errors_report_status_and_body(self):
        """429/500 previously surfaced as a bare aiohttp string ("cannot connect")."""
        client = KirkHillApiClient(api_key="key")
        body = b'{"message": "Too many requests"}'

        with pytest.raises(KirkHillConnectionError, match="HTTP 429.*Too many requests"):
            await client._get(self._Session(429, body), "/api/v1/current", {"scope": "owner"})

    @pytest.mark.asyncio
    async def test_403_quotes_the_permission_message(self):
        client = KirkHillApiClient(api_key="key")
        body = b'{"message": "This key may not read site data"}'

        with pytest.raises(KirkHillPermissionError, match="may not read site data"):
            await client._get(self._Session(403, body), "/api/v1/current", {"scope": "site"})


class TestKeyShape:
    """A 401 on a freshly issued key is undecidable without the key's shape.

    "The dashboard rejected its own key" and "we sent the wrong bytes" produce
    the identical error; length and format separate them. These also pin the
    harder rule: the description must never contain the key.
    """

    def test_reports_length_and_format_but_not_the_key(self):
        key = "kh_live_abcdEFGH1234567890"
        described = describe_key(key)

        assert f"{len(key)}-char value" in described
        assert "matches the kh_live_ API-key format" in described
        assert "abcdEFGH1234567890" not in described, (
            "The description lands in the log, an abort message and a bug "
            "report -- none of which may carry key material."
        )

    def test_flags_whitespace_at_the_edges(self):
        described = describe_key("  kh_live_short  ")

        assert "4 whitespace character(s)" in described
        assert "matches the kh_live_ API-key format" in described
        # The whitespace itself is the finding: it makes the API answer
        # "not valid" while every other part of the request is correct.
        assert "kh_live_short" not in described

    def test_reports_a_value_that_is_not_a_kh_live_key(self):
        described = describe_key("eyJhbGciOiJIUzI1NiJ9.payload-signature")

        assert "does not start with kh_live_" in described
        assert "eyJ" not in described

    def test_reports_a_key_with_unexpected_characters(self):
        described = describe_key("kh_live_has spaces inside")

        assert "starts with kh_live_ but contains other characters" in described
        assert "has spaces inside" not in described

    def test_client_strips_whitespace_before_sending(self):
        client = KirkHillApiClient(api_key="  kh_live_padded\n")

        assert client._headers["Authorization"] == "Bearer kh_live_padded", (
            "A trailing newline in the Authorization header is enough for the API to reply 'The API key is not valid.'"
        )


class TestGetTurbinesDefaultRange:
    """The default must be a range the endpoint actually serves."""

    def test_default_range_is_served_by_the_endpoint(self):
        """docs/api.md: only today and all are known to work on /turbines.

        The spec advertises the full Range set for that endpoint, but the
        intermediate values are not served -- so a "7d" default turned every
        bare get_turbines() call into a 422 the caller had to diagnose. Both
        call sites pass an explicit range, which is why this stayed latent.
        """
        default = inspect.signature(KirkHillApiClient.get_turbines).parameters["range_value"].default
        assert default in {"today", "all"}, f"get_turbines must default to a range the endpoint serves, got {default!r}"
