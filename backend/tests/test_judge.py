"""Regression tests use authentic recorded NASA responses, never synthetic physics."""

import hashlib
import io
import json
import zipfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.judge import JudgeRequest, calculate, recorded
from app.main import app


def inputs(**overrides):
    d, _ = recorded()
    return dict(
        dataset_id=d.metadata.dataset_id,
        cell_ids=[c.cell_id for c in d.cells],
        original_cell_id=d.cells[0].cell_id,
        start_utc="2026-11-15T00:00:00Z",
        end_utc="2026-11-22T00:00:00Z",
        step_minutes=60,
        minimum_shared_minutes=60,
        filters={"qualities": ["source_lola_count_and_uncertainty_not_supplied"]},
        **overrides,
    )


def test_original_delayed_authentic_sources_and_equal_duration():
    result = calculate(JudgeRequest(**inputs()))
    assert result["outcome"] == "KEEP"
    for original, delayed in zip(result["original"]["results"], result["delayed"]["results"]):
        a, b = original["dynamic_vector"], delayed["dynamic_vector"]
        assert a["horizon_model"] == b["horizon_model"] == "GEOMETRIC_IDEAL"
        assert (
            datetime.fromisoformat(b["start_utc"]) - datetime.fromisoformat(a["start_utc"])
        ).total_seconds() == 7 * 86400
        assert (
            datetime.fromisoformat(b["end_utc"]) - datetime.fromisoformat(a["end_utc"])
        ).total_seconds() == 7 * 86400
        assert b["features"]["longest_shared_minutes"] == 168 * 60
        assert a["features"]["longest_shared_minutes"] / 60 == pytest.approx(99.82, abs=0.02)
        assert len(a["records"]) == len(b["records"]) == 169
        for d in (a, b):
            assert d["observer"]["altitude_km"] == 0
            assert d["observer"]["latitude_deg"] == original["cell"]["latitude_deg"]
            assert d["observer"]["longitude_east_deg"] == original["cell"]["longitude_deg"] % 360
            assert d["sampling_cadence_minutes"] == 60
            assert not d["missing_data"]
            for q in d["provenance"]["queries"].values():
                assert q["delivery"] == "VERIFIED_CACHE"
                assert len(q["raw_sha256"]) == 64
                assert "ssd.jpl.nasa.gov" in q["source_url"]


def test_missing_ephemeris_remains_unknown():
    req = inputs()
    req.update(start_utc="2027-01-01T00:00:00Z", end_utc="2027-01-08T00:00:00Z")
    result = calculate(JudgeRequest(**req))
    assert result["outcome"] == "INSUFFICIENT DATA"
    assert result["selected"] is None
    assert all(r["dynamic_vector"] is None for r in result["delayed"]["results"])


def test_unsupported_terrain_and_constraints_are_not_ranked():
    req = inputs(horizon_model="TERRAIN_PARTIAL", terrain_site_id="unavailable")
    assert not calculate(JudgeRequest(**req))["delayed"]["comparison"]["ranked"]
    req = inputs()
    req["filters"]["maximum_slope_deg"] = 0
    assert not calculate(JudgeRequest(**req))["delayed"]["comparison"]["ranked"]


def test_export_preserves_exact_evaluated_results_and_hash():
    with TestClient(app) as web:
        response = web.post("/api/v1/judge/evaluate", json=inputs())
        assert response.status_code == 200, response.text
        result = response.json()
        response = web.post("/api/v1/judge/report", json={"evidence_id": result.pop("evidence_id")})
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            evidence = archive.read("evidence.json")
            assert json.loads(evidence)["result"] == result
            report = archive.read("report.md").decode()
            assert hashlib.sha256(evidence).hexdigest() in report
            assert "summary.svg" in report
            assert "censored" in report
            assert archive.read("summary.svg").startswith(b"<svg")
        missing = web.post("/api/v1/judge/report", json={"evidence_id": "0" * 64})
        assert missing.status_code == 404


def test_reject_duplicate_identity_unknown_fields_and_unselected_original():
    with TestClient(app) as web:
        req = inputs()
        req["cell_ids"] *= 2
        assert web.post("/api/v1/judge/evaluate", json=req).status_code == 422
        req = inputs()
        req["invented_slope"] = 0
        assert web.post("/api/v1/judge/evaluate", json=req).status_code == 422
        req = inputs()
        req["original_cell_id"] = "unselected"
        assert web.post("/api/v1/judge/evaluate", json=req).status_code == 422


def test_source_cells_and_metadata_are_unmodified():
    d, _ = recorded()
    with TestClient(app) as web:
        response = web.get("/api/v1/judge/dataset").json()
    assert response["dataset_sha256"] == d.digest
    assert response["cells"] == [c.model_dump(mode="json") for c in d.cells]
    assert response["metadata"] == d.metadata.model_dump(mode="json")
