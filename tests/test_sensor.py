"""Tests for sensors — timeframe labels, energy display helper."""
from __future__ import annotations

from custom_components.kirkhill_wind.sensor import (
    TIMEFRAME_LABELS,
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
            assert not key.startswith("year_"), (
                f"Remove hard-coded '{key}' — _timeframe_label handles it dynamically"
            )

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
