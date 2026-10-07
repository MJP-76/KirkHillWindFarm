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
    SCOPE_OWNER,
    SCOPE_SITE,
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
    # HomeAssistant.services is assigned in __init__, not on the class, so
    # MagicMock(spec=HomeAssistant) cannot provide it -- accessing it raises
    # AttributeError. tests/test_services.py needs a service registry.
    mock_hass.services = MagicMock()

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


def _current_turbines(scope: str) -> list[dict]:
    """Per-turbine rows exactly as /api/v1/current returns them, for one scope.

    Live state only: the current endpoint carries no generation, rotor speed
    or coordinates -- those come from /api/v1/turbines (mock_turbine_rows).
    The two endpoints share nothing but id, capacity_factor_percent and the
    capacity pair, which is why the fixture keeps them apart.
    """
    owner = scope == SCOPE_OWNER
    return [
        {
            "id": f"T{i}",
            "status": "active" if i <= 7 else "inactive",
            "state_text": (
                "Turbine in operation"
                if i <= 7
                else "Lack of wind: Wind speed too low"
            ),
            "power_kw": (0.134 if i <= 7 else 0.0) if owner else (987.0 if i <= 7 else 0.0),
            "capacity_factor_percent": 42.0 if i <= 7 else 0.0,
            "capacity_watts": 319.933125 if owner else 2350000,
            "capacity_kw": 0.3199331 if owner else 2350,
            "wind_speed_mps": 8.5,
            "latest_power_at": "2026-06-25T12:34:00Z",
            "latest_wind_speed_at": "2026-06-25T12:34:00Z",
            "status_started_at": "2026-06-25T12:00:00Z",
            "state_started_at": "2026-06-25T12:00:00Z",
        }
        for i in range(1, 9)
    ]


def _current_payload(scope: str) -> dict:
    """A /api/v1/current response for one scope, with that scope's own numbers.

    Owner and site differ exactly where the API makes them differ --
    reading.scope, capacity, power and the per-turbine rows. One payload for
    both scopes lied twice: it reported reading.scope="owner" for the site
    request, and made the owner share read 100% where production reads
    0.013614%. The capacity pair below is the production ratio, so the share
    derived from these two payloads matches the live figure exactly.
    """
    owner = scope == SCOPE_OWNER
    return {
        "reading": {
            "scope": scope,
            "source_interval": "1m",
            "generated_at": "2026-06-25T12:34:00Z",
            "complete": True,
        },
        "summary": {
            "total_power_kw": 0.941 if owner else 6909.0,
            "total_power_watts": 941 if owner else 6909000,
            "wind_speed_mps": 8.5,
            "capacity_factor_percent": 36.75,
            "active_turbines": 7,
            "inactive_turbines": 1,
            "unknown_turbines": 0,
            "total_turbines": 8,
            "capacity_watts": 2559.465 if owner else 18800000,
            "capacity_kw": 2.559465 if owner else 18800,
            "latest_power_at": "2026-06-25T12:34:00Z",
            "latest_wind_speed_at": "2026-06-25T12:34:00Z",
            "latest_status_at": "2026-06-25T12:00:00Z",
            "total_generation_kwh_today": 22.88 if owner else 168062.0,
            "total_generation_wh_today": 22880 if owner else 168062000,
        },
        "turbines": _current_turbines(scope),
    }


@pytest.fixture
def mock_current_turbines():
    """The site-scope per-turbine rows, for tests that want them directly."""
    return _current_turbines(SCOPE_SITE)


@pytest.fixture
def mock_current_payload():
    """The site-scope /api/v1/current response.

    Owner and site are different payloads; mock_api_client answers each
    request with its own (see _current_payload). This fixture stays
    site-shaped because the one test that uses it directly does so for the
    site call.
    """
    return _current_payload(SCOPE_SITE)


@pytest.fixture
def mock_turbine_rows():
    """Rows exactly as /api/v1/turbines returns them.

    Scoped generation, rotor speed and coordinates -- and no live power or
    state, which is /api/v1/current's job. The coordinator builds
    turbine_generation and the coordinate map from these.
    """
    return [
        {
            "id": f"T{i}",
            "generation_kwh": 3600.0,
            "generation_share_percent": 12.5,
            "capacity_factor_percent": 42.0,
            "latest_generation_interval_end": "2026-06-25T12:30:00Z",
            "latest_rotor_speed_rpm": 12.3,
            "latest_rotor_speed_at": "2026-06-25T12:34:00Z",
            "coordinates": {
                "latitude": 55.3047599 + i * 0.001,
                "longitude": -4.7458191 + i * 0.001,
                "source": "OpenStreetMap",
                "openstreetmap_node_id": 12134002376 + i,
            },
        }
        for i in range(1, 9)
    ]


@pytest.fixture
def mock_summary_payload():
    """Return a realistic /api/v1/summary response.

    Every key here exists in the live payload; `latest_import_status` is
    "success"/"running", never "completed" -- that string only ever appeared
    in the stale openapi.yaml example.
    """
    return {
        "summary": {
            "total_generation_kwh": 50000.0,
            "capacity_factor_percent": 38.5,
            "active_turbines": 8,
            "capacity_watts": 18800000,
            "capacity_kw": 18800,
            "co2_avoided_kg": 4500.0,
            "co2_avoided_assumed_export_factor": 0.99,
            "co2_avoided_coverage_percent": 98.11,
            "co2_avoided_matched_intervals": 311,
            "co2_avoided_expected_intervals": 317,
            "co2_avoided_complete": False,
            "latest_carbon_intensity_at": "2026-06-25T12:00:00Z",
            "latest_generation_interval_end": "2026-06-25T12:30:00Z",
            "latest_import_status": "success",
        },
        "window": {
            "range": "30d",
            "from": "2025-01-01T00:00:00Z",
            "to": "2025-01-31T23:59:59Z",
            "bucket": "10m",
            "scope": "site",
        },
    }


@pytest.fixture
def mock_api_client(mock_current_payload, mock_turbine_rows, mock_summary_payload):
    """Return a mock KirkHillApiClient with endpoint-shaped responses."""
    client = AsyncMock()
    client.get_current = AsyncMock(
        side_effect=lambda session, scope: _current_payload(scope)
    )
    client.get_turbines = AsyncMock(return_value=mock_turbine_rows)
    client.get_summary = AsyncMock(return_value=mock_summary_payload)
    client.get_wind_speed = AsyncMock(
        return_value={
            "series": [
                {"wind_speed_mps": 8.5, "timestamp": "2025-01-15T12:00:00Z"},
            ],
        }
    )
    client.test = AsyncMock()
    return client
