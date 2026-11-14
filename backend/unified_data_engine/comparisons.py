"""Explicit bounded scenarios, same cells/models, and an exact seven-day delay."""

import math
from datetime import timedelta
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .errors import DatasetError
from .schemas import AnalysisRequest


class ComparisonRequest(AnalysisRequest):
    cell_ids: list[str] = Field(min_length=2, max_length=4)
    delay_hours: Literal[168] = 168

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.cell_ids)) != len(self.cell_ids):
            raise ValueError("Comparison cell IDs must be unique")
        return self


def compare(service, dataset_id, request):
    # Validate every cell, interval and budget before any NASA calls.
    dataset = service.registry.get(dataset_id)
    query = request.at(0, 0)
    if (query.end_utc - query.start_utc).total_seconds() > 48 * 3600:
        raise DatasetError(
            "COMPARISON_BUDGET", "Comparisons are bounded to a 48-hour study interval"
        )
    if len(query.timestamps()) * len(request.cell_ids) * 2 > 2000:
        raise DatasetError("COMPARISON_BUDGET", "At most 2000 combined scenario timestamps")
    vectors = service.vectors(dataset_id)
    selected = [vectors.get(cell_id) for cell_id in request.cell_ids]
    if not all(row["valid"] for row in selected):
        raise DatasetError("INVALID_VECTOR", "All comparison cells must have valid terrain")
    if len({row["calculation_version"] for row in selected}) != 1:
        raise DatasetError(
            "INCOMPATIBLE_CALCULATION_VERSION", "Selected terrain calculation versions differ"
        )
    for cell_id in request.cell_ids:
        dataset.get_cell(cell_id)
    base_values = request.model_dump(exclude={"cell_ids", "delay_hours"})
    delayed = base_values | dict(
        start_utc=(query.start_utc + timedelta(hours=168)).isoformat(),
        end_utc=(query.end_utc + timedelta(hours=168)).isoformat(),
    )
    try:
        delayed_request = AnalysisRequest(**delayed)
    except ValidationError as exc:
        raise DatasetError(
            "INVALID_REQUEST", "Delayed interval is outside the supported UTC range"
        ) from exc
    delayed_request.at(0, 0)  # Also validate the delayed dates before querying.
    original_request = AnalysisRequest(**base_values)
    results = {}
    for label, scenario_request in (
        ("original", original_request),
        ("delayed_168h", delayed_request),
    ):
        results[label] = [
            service.analyze(dataset_id, cell_id, scenario_request) for cell_id in request.cell_ids
        ]
    reference = selected[0]
    distances = [
        dict(
            cell_id=row["cell_id"],
            normalized_terrain_distance=math.sqrt(
                math.fsum(
                    (a - b) ** 2
                    for a, b in zip(
                        reference["normalized_values"], row["normalized_values"], strict=True
                    )
                )
            ),
        )
        for row in selected[1:]
    ]
    return dict(
        contract_version="1.0",
        dataset_id=dataset_id,
        model="GEOMETRIC_IDEAL_LINEAR_V1",
        delay_hours=168,
        reference_cell_id=request.cell_ids[0],
        normalization_fit_sha256=vectors.fit["fit_sha256"],
        terrain_distances=distances,
        scenarios={
            key: [result.model_dump(mode="json") for result in rows]
            for key, rows in results.items()
        },
        interpretation="Comparisons use identical UTC intervals per scenario, cadence, observer settings and geometry model; no mission ranking or terrain clearance is inferred",
    )
