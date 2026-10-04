"""The fixtures and openapi.yaml must describe the API that actually runs.

Both drifted in opposite directions before this file existed: the spec
required ``site_capacity_watts`` (never sent) and, with
``additionalProperties: false``, forbade ``capacity_watts`` (always sent),
while the fixtures invented ``generation_kwh``, ``coordinates`` and
``latest_rotor_speed_rpm`` on the *current* endpoint, which only
``/api/v1/turbines`` returns. openapi.yaml has since been corrected against a
real diagnostics payload; these assertions pin the fixtures to it, so neither
side can drift silently again.

PyYAML arrives with Home Assistant itself, so no extra test dependency.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
SCHEMAS = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))["components"]["schemas"]


def _resolve(schema: dict) -> dict:
    """Follow a single ``$ref`` so nested schemas can be asserted directly."""
    ref = schema.get("$ref")
    if not ref:
        return schema
    return SCHEMAS[ref.rsplit("/", 1)[-1]]


def _assert_matches(schema: dict, payload: dict, label: str) -> None:
    """Assert payload satisfies a schema that declares ``additionalProperties: false``.

    Two failure modes, both of which are drift: a key the spec does not
    document, and a key the spec requires that the payload omits.
    """
    schema = _resolve(schema)
    documented = set(schema.get("properties", {}))
    undocumented = sorted(set(payload) - documented)
    unsatisfied = sorted(set(schema.get("required", [])) - set(payload))
    assert not undocumented, (
        f"{label}: keys the spec does not document (the schema is additionalProperties: false): {undocumented}"
    )
    assert not unsatisfied, f"{label}: keys the spec requires are missing: {unsatisfied}"


class TestFixturesMatchTheSpec:
    """Every fixture payload must satisfy its schema in openapi.yaml."""

    def test_current_response(self, mock_current_payload):
        _assert_matches(SCHEMAS["CurrentResponse"], {"data": mock_current_payload}, "CurrentResponse")
        _assert_matches(
            SCHEMAS["CurrentResponse"]["properties"]["data"],
            mock_current_payload,
            "current data",
        )
        _assert_matches(
            SCHEMAS["CurrentReading"],
            mock_current_payload["reading"],
            "current reading",
        )
        _assert_matches(
            SCHEMAS["CurrentSummary"],
            mock_current_payload["summary"],
            "current summary",
        )
        for row in mock_current_payload["turbines"]:
            _assert_matches(SCHEMAS["CurrentTurbine"], row, f"current turbine {row.get('id')}")

    def test_turbine_rows(self, mock_turbine_rows):
        """The /api/v1/turbines rows carry generation, rotor and coordinates."""
        for row in mock_turbine_rows:
            _assert_matches(SCHEMAS["Turbine"], row, f"turbine row {row.get('id')}")

    def test_summary_response(self, mock_summary_payload):
        _assert_matches(SCHEMAS["SummaryResponse"], {"data": mock_summary_payload}, "SummaryResponse")
        _assert_matches(
            SCHEMAS["SummaryResponse"]["properties"]["data"],
            mock_summary_payload,
            "summary data",
        )
        _assert_matches(SCHEMAS["Summary"], mock_summary_payload["summary"], "summary")
        _assert_matches(SCHEMAS["Window"], mock_summary_payload["window"], "window")
