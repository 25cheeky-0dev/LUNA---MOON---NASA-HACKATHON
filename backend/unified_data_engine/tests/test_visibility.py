"""Explicit missing-observation and partial-coverage behavior, not fabricated science."""

from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient
from unified_data_engine.schemas import AnalysisRequest
from unified_data_engine.visibility import visibility

from .conftest import FIXTURES


def test_partial_terrain_never_becomes_confirmed_visibility():
    request = AnalysisRequest(start_utc="2026-11-15T00:00:00Z", end_utc="2026-11-16T00:00:00Z")
    query = request.at(-89.7787655990766, 192.48248938495448)
    result = CelestialService(HorizonsClient(FIXTURES / "horizons", offline=True)).ephemeris(query)
    profile = dict(coverage="PARTIAL", far_field_complete=False, azimuth_samples=[])
    data = visibility(result, request, profile)
    assert all(r["terrain"] == dict(sun="UNKNOWN", earth="UNKNOWN") for r in data["samples"])
    assert data["terrain_known_fraction"] == 0
    assert data["geometric_window_summary"]["known_fraction"] == 1
    # Deliberately injected missing observation; only this test copy is changed.
    result = result.model_copy(deep=True)
    result.records[1].sun_elevation_deg = None
    result.records[1].valid = False
    result.records[1].quality = "MISSING_OBSERVATION"
    data = visibility(result, request, profile)
    assert data["samples"][1]["geometric"]["sun"] == "UNKNOWN"
    assert data["geometric_window_summary"]["unknown_fraction"] > 0
