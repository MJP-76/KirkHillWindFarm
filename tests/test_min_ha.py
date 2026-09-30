"""Tests for the declared minimum Home Assistant version.

`scripts/version_sync.py` owns MIN_HA_VERSION and CI installs that exact
release in the `min-ha` job. These tests catch the cheaper failure: someone
editing hacs.json or requirements.txt by hand and leaving the declared floor
inconsistent with the constant, or moving the floor without saying why.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _version_tuple(raw: str) -> tuple[int, int, int]:
    """Turn "2026.1.0" into (2026, 1, 0) so floors can be compared."""
    major, minor, patch = raw.split(".")
    return (int(major), int(minor), int(patch))


def _months(raw: str) -> int:
    """Total months since year 0, so two Home Assistant releases can be diffed."""
    major, minor, _ = _version_tuple(raw)
    return major * 12 + minor


def _load_version_sync():
    """Import scripts/version_sync.py without requiring it to be a package."""
    spec = importlib.util.spec_from_file_location(
        "version_sync", ROOT / "scripts" / "version_sync.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def version_sync():
    return _load_version_sync()


class TestMinimumHomeAssistant:
    """The advertised floor must be consistent everywhere it is declared."""

    def test_hacs_json_matches_min_ha_version(self, version_sync):
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        assert hacs["homeassistant"] == version_sync.MIN_HA_VERSION, (
            f"hacs.json advertises Home Assistant {hacs['homeassistant']} but "
            f"version_sync.MIN_HA_VERSION is {version_sync.MIN_HA_VERSION}"
        )

    def test_requirements_txt_matches_min_ha_version(self, version_sync):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        match = re.search(r"^homeassistant>=([\d.]+)$", text.strip(), re.MULTILINE)
        assert match, "requirements.txt must pin 'homeassistant>=X.Y.Z'"
        assert match.group(1) == version_sync.MIN_HA_VERSION

    def test_min_ha_version_is_a_plain_release(self, version_sync):
        assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", version_sync.MIN_HA_VERSION), (
            f"MIN_HA_VERSION={version_sync.MIN_HA_VERSION} must be a plain Home "
            "Assistant release like 2026.1.0, not a branch, rc or wildcard"
        )

    def test_min_ha_python_is_declared(self, version_sync):
        """A Python floor is required, or pip silently installs a different HA."""
        assert re.fullmatch(r"3\.\d+", version_sync.MIN_HA_PYTHON)

    def test_min_ha_python_is_not_newer_than_ha_requires(self, version_sync):
        """Guard against the silent-backtrack trap.

        Each Home Assistant release declares its own requires-python. If the
        CI Python is older than the pinned HA requires, pip resolves to some
        other, older Home Assistant and the min-ha job stops testing what it
        claims to test. The assertion step in CI catches the symptom; this
        documents the coupling and fails fast if the pair is nonsensical.
        """
        # Home Assistant requires-python floors, as declared on PyPI.
        # 2025.2.0 and 2026.1.0 both require >= 3.13.x; 2026.9 requires 3.14.
        known_floors = {
            "2025.2.0": "3.13",
            "2026.1.0": "3.13",
        }
        expected = known_floors.get(version_sync.MIN_HA_VERSION)
        if expected is not None:
            assert version_sync.MIN_HA_PYTHON == expected, (
                f"MIN_HA_PYTHON={version_sync.MIN_HA_PYTHON} does not match the "
                f"Python required by Home Assistant {version_sync.MIN_HA_VERSION} "
                f"({expected}); pip would install a different HA release"
            )
        else:
            pytest.fail(
                f"MIN_HA_VERSION={version_sync.MIN_HA_VERSION} is new to this test. "
                "Add its requires-python to known_floors so the min-ha CI job "
                "cannot silently install a different Home Assistant."
            )

    def test_advertised_floor_is_not_below_the_technical_floor(self, version_sync):
        """Never advertise support older than the code can actually import.

        MIN_HA_VERSION is a deliberate policy choice and may sit above the
        technical floor. It must never sit below it.
        """
        advertised = _version_tuple(version_sync.MIN_HA_VERSION)
        technical = _version_tuple(version_sync.TECHNICAL_FLOOR_HA_VERSION)
        assert advertised >= technical, (
            f"MIN_HA_VERSION={version_sync.MIN_HA_VERSION} is below the technical "
            f"floor {version_sync.TECHNICAL_FLOOR_HA_VERSION}. HACS would offer the "
            "integration to installs that cannot import it."
        )

    def test_lovelace_data_justifies_the_technical_floor(self, version_sync):
        """Keep TECHNICAL_FLOOR_HA_VERSION honest.

        homeassistant.components.lovelace.const.LOVELACE_DATA is the newest
        symbol this integration imports, and it landed in 2025.2.0. While
        dashboard.py still imports it, the technical floor cannot be lower.

        If a refactor drops the Lovelace dependency, this test is the signal
        that the technical floor -- and possibly the advertised floor -- can
        come down.
        """
        source = (ROOT / "custom_components" / "kirkhill_wind" / "dashboard.py").read_text(
            encoding="utf-8"
        )
        if "LOVELACE_DATA" in source:
            assert version_sync.TECHNICAL_FLOOR_HA_VERSION == "2025.2.0", (
                "dashboard.py still imports LOVELACE_DATA, which requires Home "
                f"Assistant 2025.2.0, but TECHNICAL_FLOOR_HA_VERSION is "
                f"{version_sync.TECHNICAL_FLOOR_HA_VERSION}. If that import is "
                "gone, lower both floors deliberately and re-run the min-ha job."
            )

    def test_advertised_floor_is_not_pointlessly_high(self, version_sync):
        """The floor should stay close to the technical floor, not drift upward.

        MIN_HA_VERSION is allowed to sit above TECHNICAL_FLOOR_HA_VERSION for
        access to newer HA APIs. It should not creep arbitrarily far above it,
        or the integration quietly stops being installable for no reason.

        Two years of slack is generous for a deliberate choice; beyond that,
        re-justify it or lower it.
        """
        delta = _months(version_sync.MIN_HA_VERSION) - _months(
            version_sync.TECHNICAL_FLOOR_HA_VERSION
        )
        assert delta <= 24, (
            f"MIN_HA_VERSION={version_sync.MIN_HA_VERSION} is {delta} months above "
            f"the technical floor {version_sync.TECHNICAL_FLOOR_HA_VERSION}. Lower it "
            "or record why the extra reach is worth blocking installs."
        )
