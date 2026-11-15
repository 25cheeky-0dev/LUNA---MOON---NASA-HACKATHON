"""Curated presentation adapter; all physical results use the existing engine."""

import hashlib
import io
import json
import os
import threading
import zipfile
from collections import OrderedDict
from functools import lru_cache
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import Field, model_validator

from app.integration.api import DelayRequest, engine
from app.integration.contracts import DelayResponse
from app.integration.engine import AnalysisEngine, Scenario
from app.integration.grid import Dataset
from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient
from celestial_engine.schemas import StrictModel

router = APIRouter(prefix="/api/v1/judge", tags=["judge-presentation"])
ROOT = Path(__file__).resolve().parents[2]
gate = threading.BoundedSemaphore(2)
reports = OrderedDict()
report_lock = threading.Lock()


@lru_cache(maxsize=1)
def recorded():
    dataset = Dataset.read(ROOT / "docs/evidence/unified/real_v3_two_cells.json")
    registry = SimpleNamespace(datasets={dataset.metadata.dataset_id: dataset}, errors=[])
    client = HorizonsClient(ROOT / "backend/tests/fixtures/unified_nasa", offline=True)
    return dataset, AnalysisEngine(registry, CelestialService(client))


class JudgeRequest(DelayRequest):
    source_mode: Literal["recorded", "configured"] = "recorded"
    # Keep the curated synchronous workload bounded; the existing API is unchanged.
    cell_ids: list[str] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def presentation_budget(self):
        if len(self.timestamps()) * len(self.cell_ids) > 2000:
            raise ValueError(
                "Judge Mode supports at most 2000 samples across selected cells per study"
            )
        return self


@router.get("/dataset")
def dataset():
    try:
        d, _ = recorded()
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Recorded scientific assets are unavailable") from exc
    return dict(
        metadata=d.metadata.model_dump(),
        cells=[c.model_dump() for c in d.cells],
        dataset_sha256=d.digest,
        source_mode="recorded",
        note="Authentic extracted Site04 cells. Recorded NASA responses are checked and recomputed; no synthetic fallback.",
        ai_status="CONFIGURED_NOT_TESTED"
        if any(os.getenv(p + "_API_KEY") and os.getenv(p + "_MODEL") for p in ("GROQ", "NVIDIA"))
        else "UNCONFIGURED",
    )


def calculate(request):
    if not gate.acquire(blocking=False):
        raise HTTPException(429, "Analysis capacity reached; retry after the current request")
    try:
        selected = recorded()[1] if request.source_mode == "recorded" else engine()
        scenario = Scenario.model_validate(
            request.model_dump(exclude={"source_mode", "original_cell_id"})
        )
        result = selected.delay(scenario, request.original_cell_id)
        return DelayResponse.model_validate(result).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(
            404, "Dataset or cell is not available in the chosen source mode"
        ) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(422, "Scientific evaluation unavailable: " + str(exc)) from exc
    finally:
        gate.release()


class JudgeResult(DelayResponse):
    evidence_id: str


class ReportRequest(StrictModel):
    evidence_id: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/evaluate", response_model=JudgeResult)
def evaluate(request: JudgeRequest):
    result = calculate(request)
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    with report_lock:
        reports[key] = (result, request)
        reports.move_to_end(key)
        while len(reports) > 16:
            reports.popitem(last=False)
    return dict(result, evidence_id=key)


def report_files(result, request):
    evidence = json.dumps(
        dict(request=request.model_dump(mode="json"), result=result), indent=2, allow_nan=False
    ).encode()
    digest = hashlib.sha256(evidence).hexdigest()
    lines = [
        "# WISPR — reproducible mission comparison",
        "",
        "![Comparison summary](summary.svg)",
        "",
        f"Source mode: **{request.source_mode}**. Outcome: **{result['outcome']}**.",
        "",
        result["reason"],
        "",
        "| Scenario | Cell | Longest shared / h | Unknown fraction |",
        "|---|---|---:|---:|",
    ]
    height = 180 + 48 * sum(len(result[name]["results"]) for name in ("original", "delayed"))
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}">',
        f'<rect width="1100" height="{height}" fill="#0b171e"/><g fill="#edf2ed" font-family="sans-serif">',
        '<text x="32" y="45" font-size="25">WISPR / Original vs +7 days</text>',
    ]
    y = 90
    for name in ("original", "delayed"):
        group = result[name]
        for row in group["results"]:
            d = row["dynamic_vector"]
            minutes = d["features"]["longest_shared_minutes"] if d else None
            value = "Unknown" if minutes is None else f"{minutes / 60:.2f}"
            unknown = d["features"]["unknown_data_fraction"] if d else "Unknown"
            lines.append(f"| {name} | {row['cell_id']} | {value} | {unknown} |")
            svg.append(
                f'<text x="32" y="{y}">{escape(name + " / " + row["cell_id"] + " / " + value + " h")}</text>'
            )
            if d and minutes is not None:
                from datetime import datetime

                total = (
                    datetime.fromisoformat(d["end_utc"]) - datetime.fromisoformat(d["start_utc"])
                ).total_seconds() / 60
                width = 300 * max(0, min(1, minutes / total))
                svg.append(
                    f'<rect x="740" y="{y - 16}" width="300" height="16" fill="#223c46"/><rect x="740" y="{y - 16}" width="{width:.3f}" height="16" fill="#e5c085"/>'
                )
            y += 48
    svg.extend(
        [
            f'<text x="32" y="{height - 65}">Ideal geometry is not electrical power, radio communication or landing safety.</text>',
            f'<text x="32" y="{height - 30}">A full-window result is capped by the study duration. See evidence.json for all assumptions.</text>',
            "</g></svg>",
        ]
    )
    lines += [
        "",
        "## Selected terrain measurements",
        "",
        "| Cell | Latitude / deg | Longitude east / deg | Elevation / m | Slope / deg | Roughness / m |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["original"]["results"]:
        c = row["cell"]
        values = [
            c.get(k)
            for k in ("latitude_deg", "longitude_deg", "elevation_m", "slope_deg", "roughness_m")
        ]
        lines.append(
            "| "
            + row["cell_id"]
            + " | "
            + " | ".join("Unknown" if v is None else str(v) for v in values)
            + " |"
        )
    lines += [
        "",
        "Elevation is cell-mean source height, slope is mean native-pixel gradient angle, and roughness is the RMS residual from a fitted plane. The preserved dataset metadata defines the exact methods and sampling scale.",
        "",
    ]
    lines += [
        "",
        "## Inputs and methodology",
        "",
        "```json",
        json.dumps(request.model_dump(mode="json"), indent=2),
        "```",
        "",
        "Exact seven-day shift; equal study durations. Piecewise-linear boundaries between adjacent samples; missing samples remain unknown.",
        "Timing resolution is the stated cadence, not the printed decimal precision. Differences below one cadence do not establish superiority.",
        "GEOMETRIC_IDEAL uses target-center elevation above zero. TERRAIN_PARTIAL cannot certify an unobstructed far-field skyline.",
        "Horizons altitude is relative to its lunar reference; DEM elevation is not substituted. The observer-height setting applies to the terrain engine only.",
        "Full-window visibility is censored at the evaluation endpoints, not a prediction beyond them.",
        "",
        "## Reproduce and verify",
        "",
        "POST the request in evidence.json to /api/v1/judge/evaluate. Recorded mode requires the matching checked NASA cache; unsupported dates remain unknown.",
        f"evidence.json SHA-256: `{digest}`",
        "",
        "evidence.json retains raw source hashes, request URLs, observer coordinates, source versions, static values, model settings, intervals, exclusions and limitations.",
        "Terrain is an interpolated LOLA DEM; missing shot counts and elevation uncertainty remain unknown. No landing-safety certification.",
        "",
        "## Source records",
        "",
    ]
    for name in ("original", "delayed"):
        for row in result[name]["results"]:
            d = row["dynamic_vector"]
            if d:
                for body, q in d["provenance"]["queries"].items():
                    lines.append(
                        f"- {name} / {row['cell_id']} / {body}: {q['delivery']}; SHA-256 `{q['raw_sha256']}`; {q['source_url']}"
                    )
    return {
        "report.md": "\n".join(lines).encode(),
        "summary.svg": "".join(svg).encode(),
        "evidence.json": evidence,
    }


@router.post("/report")
def report(request: ReportRequest):
    with report_lock:
        stored = reports.get(request.evidence_id)
    if stored is None:
        raise HTTPException(404, "Report expired or server restarted; reevaluate the comparison")
    result, inputs = stored
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in report_files(result, inputs).items():
            archive.writestr(name, content)
    return Response(
        stream.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="WISPR-research-report.zip"'},
    )
