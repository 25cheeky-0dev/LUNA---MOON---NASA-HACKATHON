"""Explicit live NASA + original V3 raster API demonstration; never an offline claim."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient
from unified_data_engine.api import get_service
from unified_data_engine.registry import DatasetRegistry
from unified_data_engine.service import UnifiedDataService

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("WISPR_V3_LIVE_TEST") != "1",
        reason="Set WISPR_V3_LIVE_TEST=1 and WISPR_V3_PACKAGE for real NASA/raster test",
    ),
]


def test_real_v3_selected_cells_original_and_delayed(tmp_path):
    from app.main import app

    root = os.environ["WISPR_V3_PACKAGE"]
    registry = DatasetRegistry([dict(dataset_id="site04-v3", root=root, adapter="site04-v3")])
    cache = tmp_path / "nasa"
    service = UnifiedDataService(registry, CelestialService(HorizonsClient(cache)))
    app.dependency_overrides[get_service] = lambda: service
    request = dict(
        cell_id="SITE04_R000_C000",
        start_utc="2026-11-15T00:00:00Z",
        end_utc="2026-11-16T00:00:00Z",
        step_minutes=60,
    )
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/data/datasets").json()["datasets"][0]["cell_count"] == 400
            response = client.post("/api/v1/data/datasets/site04-v3/analysis", json=request)
            assert response.status_code == 200, response.text
            analysis = response.json()
            assert analysis["cell"]["cell_id"] == request["cell_id"]
            assert analysis["cell"]["terrain"]["elevation_m"] == 1072.0976434326171
            assert analysis["observer"]["latitude_deg"] == -89.7787655990766
            assert analysis["observer"]["longitude_east_deg"] == -167.51751061504552 % 360
            assert analysis["observer"]["altitude_km"] == 0
            assert len(analysis["ephemeris"]["records"]) == 25
            assert all(row["valid"] for row in analysis["ephemeris"]["records"])
            assert all(
                q["delivery"] == "LIVE"
                for q in analysis["ephemeris"]["metadata"]["queries"].values()
            )
            assert analysis["visibility"]["terrain_profile"]["coverage"] == "PARTIAL"
            assert analysis["visibility"]["terrain_profile"]["azimuth_samples"]
            assert analysis["visibility"]["terrain_visibility"] == "UNKNOWN"
            comparison_request = {k: v for k, v in request.items() if k != "cell_id"} | dict(
                cell_ids=[request["cell_id"], "SITE04_R000_C001"]
            )
            comparison_response = client.post(
                "/api/v1/data/datasets/site04-v3/comparisons", json=comparison_request
            )
            assert comparison_response.status_code == 200, comparison_response.text
            comparison = comparison_response.json()
            assert comparison["delay_hours"] == 168
            assert (
                len(comparison["scenarios"]["original"])
                == len(comparison["scenarios"]["delayed_168h"])
                == 2
            )
            for scenarios in comparison["scenarios"].values():
                assert (
                    scenarios[0]["ephemeris"]["records"][0]["timestamp_utc"]
                    == scenarios[1]["ephemeris"]["records"][0]["timestamp_utc"]
                )
                assert all(
                    all(row["valid"] for row in result["ephemeris"]["records"])
                    for result in scenarios
                )
                assert all(
                    result["visibility"]["terrain_visibility"] == "UNKNOWN" for result in scenarios
                )
    finally:
        app.dependency_overrides.clear()
    output = os.getenv("WISPR_V3_DEMO_OUTPUT")
    if output:
        directory = Path(output)
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in (
            ("combined_analysis.json", analysis),
            ("comparison.json", comparison),
            ("analysis_request.json", request),
            ("comparison_request.json", comparison_request),
            ("dataset_validation.json", registry.get("site04-v3").describe()),
        ):
            (directory / name).write_bytes(json.dumps(data, indent=2, allow_nan=False).encode())
        raw_dir = directory / "nasa_cache"
        raw_dir.mkdir(exist_ok=True)
        for path in cache.glob("*.json"):
            (raw_dir / path.name).write_bytes(path.read_bytes())
