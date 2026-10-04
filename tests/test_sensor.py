"""Tests for sensors — timeframe labels, energy display helper, and new diagnostic sensors."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from custom_components.kirkhill_wind.const import SCOPE_OWNER, yearly_timeframes
from custom_components.kirkhill_wind.sensor import (
    TIMEFRAME_LABELS,
    DataGeneratedAtSensor,
    FarmGenerationByTimeframeSensor,
    LatestImportStatusSensor,
    UnknownTurbinesSensor,
    _display_energy_from_kwh,
    _timeframe_label,
)


class TestTimeframeLabels:
    """Verify the timeframe label helper produces correct labels."""

    def test_fixed_labels(self):
        """Standard timeframes should use the static lookup."""
        assert _timeframe_label("today") == "Generation (today)"
        assert _timeframe_label("yesterday") == "Generation (yesterday)"
        assert _timeframe_label("week") == "Generation (week)"
        assert _timeframe_label("month") == "Generation (month)"
        assert _timeframe_label("ytd") == "Generation (ytd)"
        assert _timeframe_label("year") == "Generation (year)"
        assert _timeframe_label("alltime") == "Generation (alltime)"

    def test_year_labels_dynamic(self):
        """Past-year keys should produce clean year labels without hard-coding."""
        assert _timeframe_label("year_2024") == "Generation (2024)"
        assert _timeframe_label("year_2025") == "Generation (2025)"
        assert _timeframe_label("year_2026") == "Generation (2026)"
        assert _timeframe_label("year_2099") == "Generation (2099)"

    def test_no_hardcoded_year_entries_needed(self):
        """TIMEFRAME_LABELS should not contain year_YYYY entries."""
        for key in TIMEFRAME_LABELS:
            assert not key.startswith("year_"), f"Remove hard-coded '{key}' — _timeframe_label handles it dynamically"

    def test_unknown_timeframe_fallback(self):
        """Unknown timeframes should still produce a readable label."""
        assert _timeframe_label("custom_tf") == "Generation (custom_tf)"


class TestDisplayEnergyFromKwh:
    """Verify the energy display helper scales units correctly."""

    def test_kwh(self):
        unit, value = _display_energy_from_kwh(500.0)
        assert unit == "kWh"
        assert value == 500.0

    def test_mwh(self):
        unit, value = _display_energy_from_kwh(1500.0)
        assert unit == "MWh"
        assert value == 1.5

    def test_gwh(self):
        unit, value = _display_energy_from_kwh(2_500_000.0)
        assert unit == "GWh"
        assert value == 2.5

    def test_twh(self):
        unit, value = _display_energy_from_kwh(3_000_000_000.0)
        assert unit == "TWh"
        assert value == 3.0

    def test_none_value(self):
        unit, value = _display_energy_from_kwh(None)
        assert unit == "kWh"
        assert value is None

    def test_zero(self):
        unit, value = _display_energy_from_kwh(0.0)
        assert unit == "kWh"
        assert value == 0.0


class TestDataGeneratedAtSensor:
    """Verify Data Generated At parses the API timestamp."""

    def _make_sensor(self, reading):
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {"owner": {"reading": reading}}
        entry = MagicMock()
        entry.entry_id = "test"
        return DataGeneratedAtSensor(coordinator, entry)

    def test_parses_iso_timestamp(self):
        sensor = self._make_sensor({"generated_at": "2026-06-25T12:34:00Z"})
        result = sensor.native_value
        assert isinstance(result, datetime)
        assert result == datetime(2026, 6, 25, 12, 34, 0, tzinfo=timezone.utc)

    def test_none_when_no_reading(self):
        sensor = self._make_sensor(None)
        assert sensor.native_value is None

    def test_none_when_missing_generated_at(self):
        sensor = self._make_sensor({"complete": True})
        assert sensor.native_value is None

    def test_none_when_not_string(self):
        sensor = self._make_sensor({"generated_at": 12345})
        assert sensor.native_value is None


class TestUnknownTurbinesSensor:
    """Verify Unknown Turbines reads from the summary."""

    def _make_sensor(self, summary):
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {"owner": {"summary": summary}}
        entry = MagicMock()
        entry.entry_id = "test"
        return UnknownTurbinesSensor(coordinator, entry)

    def test_returns_count(self):
        sensor = self._make_sensor({"unknown_turbines": 2})
        assert sensor.native_value == 2

    def test_returns_zero(self):
        sensor = self._make_sensor({"unknown_turbines": 0})
        assert sensor.native_value == 0

    def test_none_when_missing(self):
        sensor = self._make_sensor({})
        assert sensor.native_value is None


class TestLatestImportStatusSensor:
    """Verify Latest Import Status reads from the timeframe summaries."""

    def _make_sensor(self, summaries):
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {"timeframe_summaries": summaries}
        entry = MagicMock()
        entry.entry_id = "test"
        return LatestImportStatusSensor(coordinator, entry)

    def test_returns_status(self):
        summaries = {
            "owner": {
                "today": {
                    "latest_import_status": "completed",
                    "latest_generation_interval_end": "2026-06-25T12:30:00Z",
                }
            }
        }
        sensor = self._make_sensor(summaries)
        assert sensor.native_value == "completed"

    def test_extra_attributes_include_interval_end(self):
        summaries = {
            "owner": {
                "today": {
                    "latest_import_status": "completed",
                    "latest_generation_interval_end": "2026-06-25T12:30:00Z",
                }
            }
        }
        sensor = self._make_sensor(summaries)
        attrs = sensor.extra_state_attributes
        assert attrs["latest_generation_interval_end"] == "2026-06-25T12:30:00Z"

    def test_none_when_no_summaries(self):
        sensor = self._make_sensor({})
        assert sensor.native_value is None


class TestAlltimeYearSum:
    """All time is the sum of its year frames, or the API figure with a flag.

    A year frame whose fetch failed arrives as ``{}`` (the coordinator keeps
    last-known summaries only on success) and sits in retry backoff for up to
    an hour. Skipping it silently understated All time by that whole year --
    24-40% with the real figures -- while the attribute still claimed
    ``sum_of_years``. An incomplete sum now falls back to the API's own
    ``range=all`` figure (~0.1% out) and names the gap.
    """

    def _make_sensor(self, summaries):
        coordinator = MagicMock()
        coordinator.last_update_success = True
        coordinator.data = {"timeframe_summaries": {"owner": summaries}}
        entry = MagicMock()
        entry.entry_id = "test"
        return FarmGenerationByTimeframeSensor(coordinator, entry, SCOPE_OWNER, "alltime")

    @staticmethod
    def _values() -> dict[str, float]:
        """One distinguishable value per expected year frame."""
        values = {key: 100.0 + index for index, key in enumerate(yearly_timeframes(), start=1)}
        values["year"] = 1000.0
        return values

    @staticmethod
    def _summaries(values, *, drop=(), empty=(), alltime=5000.0):
        """Build the timeframe_summaries payload for one scope."""
        summaries = {key: {"total_generation_kwh": value} for key, value in values.items() if key not in drop}
        for key in empty:
            summaries[key] = {}  # exactly what a failed fetch leaves behind
        summaries["alltime"] = {"total_generation_kwh": alltime}
        # Non-year frames must never enter the sum.
        summaries["today"] = {"total_generation_kwh": 999999.0}
        summaries["month"] = {"total_generation_kwh": 999999.0}
        return summaries

    def test_complete_sum_is_the_total_of_every_year_frame(self):
        values = self._values()
        sensor = self._make_sensor(self._summaries(values))

        assert sensor.native_value == round(sum(values.values()), 3)

        attrs = sensor.extra_state_attributes
        assert attrs["generation_source"] == "sum_of_years"
        assert "missing_year_frames" not in attrs
        assert attrs["sum_of_years_kwh"]["current"] == 1000.0
        assert len(attrs["sum_of_years_kwh"]) == len(values)

    def test_missing_year_frame_falls_back_to_the_api_figure(self):
        values = self._values()
        sensor = self._make_sensor(self._summaries(values, drop=("year",)))

        assert sensor.native_value == 5000.0, (
            "a partial sum must not be shown: the API range=all figure is "
            "about 0.1% out, a sum missing a whole year is 25-40% out"
        )

        attrs = sensor.extra_state_attributes
        assert attrs["generation_source"] == "api_alltime_missing_years"
        assert attrs["missing_year_frames"] == ["year"]

    def test_failed_frame_written_as_empty_is_treated_as_missing(self):
        values = self._values()
        sensor = self._make_sensor(self._summaries(values, empty=("year",)))

        assert sensor.native_value == 5000.0
        attrs = sensor.extra_state_attributes
        assert attrs["generation_source"] == "api_alltime_missing_years"
        assert attrs["missing_year_frames"] == ["year"]

    def test_zero_generation_is_a_value_not_a_gap(self):
        values = self._values()
        values["year"] = 0.0
        sensor = self._make_sensor(self._summaries(values))

        assert sensor.native_value == round(sum(values.values()), 3)

        attrs = sensor.extra_state_attributes
        assert attrs["generation_source"] == "sum_of_years"
        assert "missing_year_frames" not in attrs
