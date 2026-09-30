"""Tests for the API client — exception hierarchy and response parsing."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kirkhill_wind.api import KirkHillApiClient, OpenMeteoApiClient
from custom_components.kirkhill_wind.exceptions import (
    KirkHillApiError,
    KirkHillAuthError,
    KirkHillConnectionError,
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
        with pytest.raises(KirkHillApiError, match="missing 'data' key"):
            client._parse_data("not a dict")

    def test_parse_data_list_raises(self):
        client = KirkHillApiClient(api_key="key")
        with pytest.raises(KirkHillApiError, match="missing 'data' key"):
            client._parse_data([1, 2, 3])


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