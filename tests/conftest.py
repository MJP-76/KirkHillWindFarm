"""Shared fixtures for Kirk Hill Wind Farm tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.kirkhill_wind.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SITE_NAME,
)


@pytest.fixture
def hass():
    """Return a mock HomeAssistant instance."""
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import frame

    mock_hass = MagicMock(spec=HomeAssistant)
    mock_hass.data = {}
    mock_hass.config = MagicMock()
    mock_hass.config.components = set()
    mock_hass.config_entries = MagicMock()
    mock_hass.bus = MagicMock()

    # DataUpdateCoordinator.__init__ calls frame.report_usage() whenever
    # config_entry is not passed explicitly, because it then has to fall back
    # to the current_entry ContextVar. The coordinator does pass it, so this is
    # only a safety net for any other report_usage() call site.
    #
    # Both symbols below (frame.async_setup, frame._hass) exist from Home
    # Assistant 2025.6 onward, comfortably below MIN_HA_VERSION, so the
    # min-ha CI job can rely on them without a hasattr() guard. If the floor
    # ever drops below 2025.6, these hasattr() guards have to come back.
    frame.async_setup(mock_hass)
    try:
        yield mock_hass
    finally:
        # Leave no global state behind for the next test.
        frame._hass.hass = None


@pytest.fixture(autouse=True)
def mock_clientsession():
    """Stub the shared aiohttp session the coordinator fetches.

    The coordinator deliberately uses HA's shared client session rather than
    making its own. On a mock hass, async_get_clientsession() would try to
    build a real session -- reaching into the zeroconf/network integration
    and failing with KeyError: 'network'. Nothing under test here depends on
    the session itself, only on the API client that receives it.
    """
    with patch(
        "custom_components.kirkhill_wind.coordinator.async_get_clientsession",
        return_value=MagicMock(name="clientsession"),
    ):
        yield


@pytest.fixture
def mock_config_entry_data():
    """Return a config entry in the shape v8 stores it in.

    entry.data holds connection details only; every user-configurable setting
    belongs in entry.options. See settings.OPTION_KEYS for the split.
    """
    return {
        "data": {
            CONF_API_KEY: "test-api-key",
            CONF_BASE_URL: DEFAULT_BASE_URL,
        },
        "options": {
            CONF_SITE_NAME: DEFAULT_SITE_NAME,
            CONF_CREATE_DASHBOARD: DEFAULT_CREATE_DASHBOARD,
            CONF_ENABLE_PAYMENT_TRACKING: DEFAULT_ENABLE_PAYMENT_TRACKING,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        },
    }


@pytest.fixture
def mock_current_payload():
    """Return a realistic current-data API response."""
    return {
        "summary": {
            "total_power_kw": 1234.5,
            "capacity_factor_percent": 42.3,
            "active_turbines": 7,
            "inactive_turbines": 1,
            "capacity_watts": 4200000,
            "wind_speed_mps": 8.5,
        },
        "turbines": [
            {
                "id": f"T{i}",
                "status": "active" if i <= 7 else "inactive",
                "state_text": "Turbine in operation" if i <= 7 else "Lack of wind: Wind speed too low",
                "power_kw": 150.0 if i <= 7 else 0.0,
                "capacity_factor_percent": 42.0 if i <= 7 else 0.0,
                "wind_speed_mps": 8.5,
                "generation_kwh": 3600.0,
                "generation_share_percent": 12.5,
                "latest_rotor_speed_rpm": 12.3 if i <= 7 else 0.0,
                "coordinates": {
                    "latitude": 54.0 + i * 0.001,
                    "longitude": -3.0 + i * 0.001,
                    "source": "osm",
                    "openstreetmap_node_id": f"node_{i}",
                },
            }
            for i in range(1, 9)
        ],
    }


@pytest.fixture
def mock_summary_payload():
    """Return a realistic summary API response."""
    return {
        "summary": {
            "total_generation_kwh": 50000.0,
            "capacity_factor_percent": 38.5,
        },
        "window": {
            "from": "2025-01-01T00:00:00Z",
            "to": "2025-01-31T23:59:59Z",
        },
    }


@pytest.fixture
def mock_api_client(mock_current_payload, mock_summary_payload):
    """Return a mock KirkHillApiClient with default responses."""
    client = AsyncMock()
    client.get_current = AsyncMock(return_value=mock_current_payload)
    client.get_turbines = AsyncMock(return_value=mock_current_payload["turbines"])
    client.get_summary = AsyncMock(return_value=mock_summary_payload)
    client.get_wind_speed = AsyncMock(return_value={
        "series": [
            {"wind_speed_mps": 8.5, "timestamp": "2025-01-15T12:00:00Z"},
        ],
    })
    client.test = AsyncMock()
    return client
