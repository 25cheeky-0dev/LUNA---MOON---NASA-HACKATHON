"""Versioned static numerical vectors; normalization never replaces source data."""

import hashlib
import heapq
import json
import math
from copy import deepcopy

from .coordinates import finite
from .errors import DatasetError

FEATURES = ["elevation_m", "slope_deg", "roughness_m"]
UNITS = ["m", "degree", "m"]
NORMALIZATION_VERSION = "terrain-population-zscore-v1"


class TerrainVectors:
    def __init__(self, dataset):
        self.dataset, self.rows = dataset, {}
        eligible = []
        # Tile-local reads avoid materializing geometry/provenance for every fitted row.
        for tile_id in dataset.tiles:
            partition = dataset._partition(tile_id)
            columns = partition["columns"]
            for cell_id, source in partition["grid"].items():
                raw = [source[columns[name]] for name in ("elevation", "slope", "roughness")]
                valid = source[columns["valid"]] and all(finite(v) for v in raw)
                supplement = dataset._supplement.get(cell_id, {})
                self.rows[cell_id] = dict(
                    cell_id=cell_id,
                    raw_values=[v if finite(v) else None for v in raw],
                    valid=valid,
                    source_valid=source[columns["valid"]],
                    source_quality=supplement.get("quality_status", "SEE_DATASET_METADATA"),
                    calculation_version=supplement.get(
                        "calculation_method_version",
                        source.get("grid_version", dataset.manifest.dataset_version),
                    ),
                )
                if valid:
                    eligible.append(raw)
        count = len(eligible)
        means = (
            [math.fsum(row[i] for row in eligible) / count for i in range(3)]
            if count
            else [None] * 3
        )
        deviations = (
            [
                math.sqrt(math.fsum((row[i] - means[i]) ** 2 for row in eligible) / count)
                for i in range(3)
            ]
            if count
            else [None] * 3
        )
        fit = dict(
            version=NORMALIZATION_VERSION,
            method="population z-score: (value-mean)/std",
            dataset_id=dataset.manifest.dataset_id,
            dataset_version=dataset.manifest.dataset_version,
            manifest_sha256=dataset.manifest_sha256,
            fit_cell_count=count,
            dataset_snapshot_sha256=dataset.snapshot_sha256,
            feature_names=FEATURES,
            units=UNITS,
            means=means,
            population_std=deviations,
            constant_feature_policy="zero for observed constant features; missing values remain null",
        )
        fit["fit_sha256"] = hashlib.sha256(
            json.dumps(fit, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        self.fit = fit
        for row in self.rows.values():
            row["normalized_values"] = (
                [
                    0.0 if deviations[i] == 0 else (v - means[i]) / deviations[i]
                    for i, v in enumerate(row["raw_values"])
                ]
                if row["valid"]
                else [None] * 3
            )

    def get(self, cell_id):
        if cell_id not in self.rows:
            raise DatasetError(
                "CELL_NOT_FOUND", "Cell ID is not present in the numerical index", 404
            )
        return deepcopy(
            dict(
                contract_version="1.0",
                feature_names=FEATURES,
                units=UNITS,
                normalization=self.fit,
                **self.rows[cell_id],
            )
        )

    def filter(
        self,
        *,
        elevation_min_m=None,
        elevation_max_m=None,
        slope_max_deg=None,
        roughness_max_m=None,
        valid_only=True,
        offset=0,
        limit=100,
    ):
        if offset < 0 or not 1 <= limit <= 1000:
            raise DatasetError("INVALID_PAGINATION", "Offset must be nonnegative; limit 1–1000")
        result = []
        for cell_id, row in self.rows.items():
            if valid_only and not row["valid"]:
                continue
            elevation, slope, roughness = row["raw_values"]
            tests = [
                (elevation_min_m, elevation, lambda v, b: v >= b),
                (elevation_max_m, elevation, lambda v, b: v <= b),
                (slope_max_deg, slope, lambda v, b: v <= b),
                (roughness_max_m, roughness, lambda v, b: v <= b),
            ]
            if all(
                bound is None or value is not None and predicate(value, bound)
                for bound, value, predicate in tests
            ):
                result.append(cell_id)
        return dict(
            contract_version="1.0",
            total=len(result),
            offset=offset,
            limit=limit,
            cell_ids=result[offset : offset + limit],
            normalization_fit_sha256=self.fit["fit_sha256"],
        )

    def similar(self, cell_id, *, limit=10, candidate_ids=None):
        if not 1 <= limit <= 100:
            raise DatasetError("SIMILARITY_BUDGET", "Similarity limit must be 1–100")
        reference = self.get(cell_id)
        if not reference["valid"]:
            raise DatasetError(
                "INVALID_VECTOR", "Missing/invalid terrain cannot be used for similarity"
            )
        candidates = self.rows if candidate_ids is None else candidate_ids
        if candidate_ids is not None and len(candidate_ids) > 1000:
            raise DatasetError("SIMILARITY_BUDGET", "At most 1000 explicit similarity candidates")

        def distances():
            for other in candidates:
                if other not in self.rows:
                    raise DatasetError("CELL_NOT_FOUND", "Similarity candidate is absent", 404)
                row = self.rows[other]
                if (
                    other == cell_id
                    or not row["valid"]
                    or row["calculation_version"] != reference["calculation_version"]
                ):
                    continue
                distance = math.sqrt(
                    math.fsum(
                        (a - b) ** 2
                        for a, b in zip(
                            row["normalized_values"], reference["normalized_values"], strict=True
                        )
                    )
                )
                yield distance, other

        selected = [
            dict(cell_id=other, distance=distance, vector=self.get(other))
            for distance, other in heapq.nsmallest(limit, distances())
        ]
        return dict(
            contract_version="1.0",
            reference=reference,
            matches=selected,
            metric="Euclidean distance in the same dataset z-score fit and calculation version",
            scientific_interpretation="Terrain feature comparison only; not celestial similarity or landing suitability",
        )


def export_vectors(vectors, directory):
    """Persist raw physical features separately from normalized, versioned features."""
    from pathlib import Path

    import pyarrow as pa
    import pyarrow.parquet as pq

    from celestial_engine.cache import atomic_write

    directory = Path(directory)
    raw, normalized = [], []
    normalized_names = ["elevation_zscore", "slope_zscore", "roughness_zscore"]
    for row in vectors.rows.values():
        common = {
            key: row[key]
            for key in ("cell_id", "valid", "source_valid", "source_quality", "calculation_version")
        }
        raw.append(common | dict(zip(FEATURES, row["raw_values"], strict=True)))
        normalized.append(
            common | dict(zip(normalized_names, row["normalized_values"], strict=True))
        )
    metadata = json.dumps(vectors.fit, indent=2, allow_nan=False).encode()
    for name, rows, features in (
        ("terrain_vectors_raw.parquet", raw, FEATURES),
        ("terrain_vectors_normalized.parquet", normalized, normalized_names),
    ):
        schema = pa.schema(
            [
                pa.field("cell_id", pa.string()),
                pa.field("valid", pa.bool_()),
                pa.field("source_valid", pa.bool_()),
                pa.field("source_quality", pa.string()),
                pa.field("calculation_version", pa.string()),
                *[pa.field(feature, pa.float64()) for feature in features],
            ],
            metadata={b"wispr_normalization": metadata},
        )
        table = pa.Table.from_pylist(rows, schema=schema)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="NONE")
        atomic_write(directory / name, sink.getvalue().to_pybytes())
    atomic_write(directory / "normalization_metadata.json", metadata)
