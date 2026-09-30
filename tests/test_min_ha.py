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
            "MIN_HA_VERSION must be a plain Home Assistant release like 2025.2.0, "
            "not a branch, rc or wildcard"
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
        documents the coupling and fails fast if the pair is nonsensical
        (a Python floor newer than the release that introduced it).
        """
        # 2025.2.0 requires >= 3.13.0; keep the declared floor in step with it.
        known_floors = {"2025.2.0": "3.13"}
        expected = known_floors.get(version_sync.MIN_HA_VERSION)
        if expected is not None:
            assert version_sync.MIN_HA_PYTHON == expected, (
                f"MIN_HA_PYTHON={version_sync.MIN_HA_PYTHON} does not match the "
                f"Python required by Home Assistant {version_sync.MIN_HA_VERSION} "
                f"({expected}); pip would install a different HA release"
            )

    def test_lovelace_data_is_the_binding_constraint(self, version_sync):
        """Record why the floor is where it is.

        homeassistant.components.lovelace.const.LOVELACE_DATA is the newest
        symbol this integration imports; it landed in 2025.2.0. If a future
        refactor drops the lovelace dependency, this assertion is the signal
        to reconsider the floor rather than leave it needlessly high.
        """
        source = (
            ROOT / "custom_components" / "kirkhill_wind" / "dashboard.py"
        ).read_text(encoding="utf-8")
        if "LOVELACE_DATA" in source:
            assert version_sync.MIN_HA_VERSION == "2025.2.0", (
                "dashboard.py still imports LOVELACE_DATA, which requires "
                "Home Assistant 2025.2.0. Update MIN_HA_VERSION and the comment "
                "above it if the floor changes."
            )
