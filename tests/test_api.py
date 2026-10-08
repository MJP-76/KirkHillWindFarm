"""Tests for the API client — exception hierarchy and response parsing."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.kirkhill_wind.api import KirkHillApiClient, OpenMeteoApiClient
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


class TestOpenMeteoClient:
    """Verify Open-Meteo forecast summarization."""

    def test_summarize_forecast_valid(self):
        client = OpenMeteoApiClient()
        body = {
            "hourly": {
                "time": [
                    "2025-01-15T13:00",
                    "2025-01-15T14:00",
                    "2025-01-15T15:00",
                    "2025-01-15T16:00",
                ],
                "wind_speed_10m": [5.0, 6.0, 7.0, 8.0],
            },
        }
        result = client._summarize_forecast(body)
        assert result["provider"] == "open_meteo"
        assert "next_hour_wind_speed_mps" in result

    def test_summarize_forecast_missing_hourly(self):
        client = OpenMeteoApiClient()
        result = client._summarize_forecast({})
        assert result == {}

    def test_summarize_forecast_empty_speeds(self):
        client = OpenMeteoApiClient()
        body = {
            "hourly": {
                "time": [],
                "wind_speed_10m": [],
            },
        }
        result = client._summarize_forecast(body)
        assert result == {}


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
            "A 403 must not start re-auth: re-entering the same narrow key "
            "would fail the same way."
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
