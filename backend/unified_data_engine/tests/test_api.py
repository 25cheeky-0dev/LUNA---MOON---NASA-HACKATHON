from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient
from unified_data_engine.api import get_service
from unified_data_engine.service import UnifiedDataService

from .conftest import FIXTURES

REQUEST = dict(
    cell_id="SITE04_R000_C000",
    start_utc="2026-11-15T00:00:00Z",
    end_utc="2026-11-16T00:00:00Z",
    step_minutes=60,
    verified_cache_only=True,
)


@pytest.fixture
def api(registry):
    from app.main import app

    service = UnifiedDataService(
        registry, CelestialService(HorizonsClient(FIXTURES / "horizons", offline=True))
    )
    app.dependency_overrides[get_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service
    finally:
        app.dependency_overrides.clear()


def test_discovery_inspection_vectors_filters_without_astronomy(api, monkeypatch):
    client, service = api

    def forbidden(*args, **kwargs):
        raise AssertionError("Static data endpoints must never query astronomy")

    monkeypatch.setattr(service.celestial, "ephemeris", forbidden)
    assert client.get("/api/v1/data/datasets").json()["datasets"][0]["cell_count"] == 400
    cell = client.get("/api/v1/data/datasets/site04-v3/cells/SITE04_R000_C000").json()
    assert cell["source_coordinates"]["longitude"] == -167.51751061504552
    vector = client.get("/api/v1/data/datasets/site04-v3/vectors/SITE04_R000_C000").json()
    assert vector["raw_values"][0] == cell["terrain"]["elevation_m"]
    assert client.get("/api/v1/data/datasets/site04-v3/cells?slope_max_deg=5").status_code == 200
    assert client.get(
        "/api/v1/data/datasets/site04-v3/similarity?cell_id=SITE04_R000_C000&limit=2"
    ).json()["matches"]
    assert client.get("/api/v1/data/datasets/unknown").status_code == 404
    assert client.get("/api/v1/data/datasets/site04-v3/cells/unknown").status_code == 404
    assert (
        client.get(
            "/api/v1/data/datasets/site04-v3/cells?elevation_min_m=100&elevation_max_m=0"
        ).status_code
        == 422
    )
    assert client.get("/api/v1/data/datasets/site04-v3/cells?limit=1001").status_code == 422
    paths = client.get("/openapi.json").json()["paths"]
    for existing in (
        "/api/v1/ephemeris",
        "/api/v1/celestial/ephemeris",
        "/api/v1/grid",
        "/api/v1/recovery",
    ):
        assert existing in paths


def test_real_recorded_nasa_combined_response(api):
    client, _ = api
    response = client.post("/api/v1/data/datasets/site04-v3/analysis", json=REQUEST)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["cell"]["cell_id"] == REQUEST["cell_id"]
    assert result["observer"]["longitude_east_deg"] == 192.48248938495448
    assert result["cell"]["terrain"]["longitude"] == -167.51751061504552
    assert result["cell"]["terrain"]["elevation_m"] != result["observer"]["altitude_km"]
    assert result["observer"]["grid_elevation_applied"] is False
    assert len(result["ephemeris"]["records"]) == 25
    assert result["visibility"]["terrain_visibility"] == "UNKNOWN"
    assert result["visibility"]["terrain_profile"]["coverage"] == "UNAVAILABLE"
    assert result["visibility"]["geometric_window_summary"]["known_fraction"] == 1
    assert all(
        q["delivery"] == "VERIFIED_CACHE"
        for q in result["ephemeris"]["metadata"]["queries"].values()
    )
    assert result["provenance"]["celestial"] == result["ephemeris"]["metadata"]
    assert result["cell"]["provenance"]["tile_cell_record"]["elevation_uncertainty_m"] is None


def test_bounded_comparison_same_intervals_and_exact_delay(api):
    client, _ = api
    body = {k: v for k, v in REQUEST.items() if k != "cell_id"} | dict(
        cell_ids=["SITE04_R000_C000", "SITE04_R000_C001"]
    )
    response = client.post("/api/v1/data/datasets/site04-v3/comparisons", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    scenarios = result["scenarios"]
    assert len(scenarios["original"]) == len(scenarios["delayed_168h"]) == 2
    for i in range(2):
        original = scenarios["original"][i]["ephemeris"]["records"]
        delayed = scenarios["delayed_168h"][i]["ephemeris"]["records"]
        assert len(original) == len(delayed) == 25
        assert datetime.fromisoformat(delayed[0]["timestamp_utc"]) - datetime.fromisoformat(
            original[0]["timestamp_utc"]
        ) == timedelta(hours=168)
    assert (
        scenarios["original"][0]["terrain_vector"]["normalization"]
        == scenarios["original"][1]["terrain_vector"]["normalization"]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"start_utc": "2026-11-15T00:00:00"},
        {"step_minutes": 0},
        {"horizons_altitude_km": float("inf")},
        {"cell_id": "missing"},
        {"start_utc": "2026-11-16T00:00:00Z"},
    ],
)
def test_invalid_analysis_inputs(api, change):
    client, _ = api
    body = REQUEST | change
    if change.get("horizons_altitude_km") == float("inf"):
        body["horizons_altitude_km"] = "Infinity"  # Deliberate invalid-input test.
    response = client.post("/api/v1/data/datasets/site04-v3/analysis", json=body)
    assert response.status_code in (404, 422)


def test_comparison_budgets_precede_network(api, monkeypatch):
    client, service = api

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid comparisons must not query NASA")

    monkeypatch.setattr(service.celestial, "ephemeris", forbidden)
    common = {k: v for k, v in REQUEST.items() if k != "cell_id"} | dict(
        cell_ids=["SITE04_R000_C000", "SITE04_R000_C001"], verified_cache_only=False
    )
    for update in [
        dict(cell_ids=["SITE04_R000_C000"] * 2),
        dict(delay_hours=167),
        dict(end_utc="2026-11-18T00:00:00Z"),
        dict(step_minutes=1),
        dict(cell_ids=["missing", "SITE04_R000_C000"]),
    ]:
        assert client.post(
            "/api/v1/data/datasets/site04-v3/comparisons", json=common | update
        ).status_code in (404, 422)


def test_unavailable_nasa_returns_no_substitute(api, tmp_path):
    client, service = api
    service.celestial = CelestialService(HorizonsClient(tmp_path, offline=True))
    response = client.post("/api/v1/data/datasets/site04-v3/analysis", json=REQUEST)
    assert response.status_code == 503
    assert response.json()["fallback"] == "NONE"


def test_unavailable_registry_and_unknown_versions(tmp_path, monkeypatch):
    from app.main import app

    path = tmp_path / "registry.json"
    path.write_text('{"schema_version":"99.0","datasets":[]}', encoding="utf-8")
    monkeypatch.setenv("WISPR_DATASETS_CONFIG", str(path))
    get_service.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/data/datasets")
            assert response.status_code == 422
            assert response.json()["error_code"] == "UNSUPPORTED_REGISTRY_VERSION"
    finally:
        get_service.cache_clear()
