"""Tests for binary sensors — API Status sensor in particular."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.kirkhill_wind.binary_sensor import APIStatusSensor


class TestAPIStatusSensor:
    """Verify API Status reflects actual data freshness, not just coordinator success."""

    def _make_sensor(self, last_update_success, current_stale):
        """Build an APIStatusSensor with mocked coordinator data."""
        coordinator = MagicMock()
        coordinator.last_update_success = last_update_success
        coordinator.data = {
            "current_stale": current_stale,
            "summary_stale": {},
        }
        entry = MagicMock()
        entry.entry_id = "test"
        sensor = APIStatusSensor(coordinator, entry)
        return sensor

    def test_on_when_fresh_data(self):
        """API Status should be ON when update succeeded and data is fresh."""
        sensor = self._make_sensor(
            last_update_success=True,
            current_stale={"owner": False, "site": False},
        )
        assert sensor.is_on is True

    def test_off_when_update_failed(self):
        """API Status should be OFF when coordinator update failed."""
        sensor = self._make_sensor(
            last_update_success=False,
            current_stale={"owner": False, "site": False},
        )
        assert sensor.is_on is False

    def test_off_when_any_scope_stale(self):
        """API Status should be OFF when any scope has stale data."""
        sensor = self._make_sensor(
            last_update_success=True,
            current_stale={"owner": True, "site": False},
        )
        assert sensor.is_on is False

    def test_off_when_all_scopes_stale(self):
        """API Status should be OFF when all scopes are stale."""
        sensor = self._make_sensor(
            last_update_success=True,
            current_stale={"owner": True, "site": True},
        )
        assert sensor.is_on is False

    def test_always_available(self):
        """API Status should always be available, even when coordinator fails."""
        sensor = self._make_sensor(
            last_update_success=False,
            current_stale={"owner": True, "site": True},
        )
        assert sensor.available is True

    def test_extra_state_attributes_include_stale_info(self):
        """Extra attributes should expose stale state for diagnostics."""
        sensor = self._make_sensor(
            last_update_success=True,
            current_stale={"owner": True, "site": False},
        )
        attrs = sensor.extra_state_attributes
        assert "current_stale" in attrs
        assert "summary_stale" in attrs
        assert attrs["current_stale"]["owner"] is True