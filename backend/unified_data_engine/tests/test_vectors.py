import math

import pytest

from unified_data_engine.vectors import TerrainVectors


def test_raw_and_normalized_values_separate_and_repeatable(dataset):
    first, second = TerrainVectors(dataset), TerrainVectors(dataset)
    vector = first.get("SITE04_R000_C000")
    assert vector["raw_values"] == [1072.0976434326171, 32.13135594956228, 0.9163221785602584]
    assert first.fit == second.fit
    assert first.fit["fit_cell_count"] == 400
    for i in range(3):
        values = [row["normalized_values"][i] for row in first.rows.values()]
        assert math.fsum(values) / 400 == pytest.approx(0, abs=1e-12)
        assert math.fsum(v * v for v in values) / 400 == pytest.approx(1, abs=1e-12)
    assert dataset.get_cell("SITE04_R000_C000").terrain["elevation_m"] == vector["raw_values"][0]


def test_filter_and_numerical_similarity(dataset):
    vectors = TerrainVectors(dataset)
    result = vectors.filter(slope_max_deg=10, roughness_max_m=1, limit=1000)
    assert all(vectors.get(cell_id)["raw_values"][1] <= 10 for cell_id in result["cell_ids"])
    first = vectors.similar("SITE04_R000_C000", limit=5)
    second = vectors.similar("SITE04_R000_C000", limit=5)
    assert first == second and len(first["matches"]) == 5
    assert all(match["cell_id"] != "SITE04_R000_C000" for match in first["matches"])
    assert [r["distance"] for r in first["matches"]] == sorted(
        r["distance"] for r in first["matches"]
    )
    assert all(
        r["vector"]["source_quality"] == first["reference"]["source_quality"]
        for r in first["matches"]
    )


def test_separate_vector_storage_roundtrip(dataset, tmp_path):
    import json

    import pyarrow.parquet as pq

    from unified_data_engine.vectors import export_vectors

    vectors = TerrainVectors(dataset)
    export_vectors(vectors, tmp_path)
    raw = pq.read_table(tmp_path / "terrain_vectors_raw.parquet")
    normalized = pq.read_table(tmp_path / "terrain_vectors_normalized.parquet")
    assert raw.num_rows == normalized.num_rows == 400
    assert raw.column("elevation_m")[0].as_py() == 1072.0976434326171
    assert (
        normalized.column("elevation_zscore")[0].as_py()
        == vectors.get("SITE04_R000_C000")["normalized_values"][0]
    )
    assert (
        "elevation_zscore" not in raw.column_names and "elevation_m" not in normalized.column_names
    )
    assert json.loads((tmp_path / "normalization_metadata.json").read_bytes()) == vectors.fit


def test_invalid_missing_and_constant_features_are_explicit(tmp_path):
    import json

    import pyarrow as pa
    import pyarrow.parquet as pq

    from unified_data_engine.loader import ParquetDataset, sha256_file

    from .conftest import write_synthetic

    manifest = write_synthetic(tmp_path, tile_count=1)
    path = tmp_path / "tile0-grid.parquet"
    table = pq.read_table(path)
    rows = table.to_pylist()
    for row in rows:
        row["roughness_m"] = 2.0
    rows[0].update(valid=False, elevation_m=float("nan"))
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    manifest["files_sha256"][path.name] = sha256_file(path)
    (tmp_path / "dataset_manifest.json").write_bytes(json.dumps(manifest).encode())
    dataset = ParquetDataset(tmp_path)
    vectors = TerrainVectors(dataset)
    invalid = vectors.get(rows[0]["cell_id"])
    assert invalid["raw_values"][0] is None and invalid["normalized_values"] == [None] * 3
    assert len(vectors.filter()["cell_ids"]) == 5
    assert all(row["normalized_values"][2] == 0 for row in vectors.rows.values() if row["valid"])
    cell = dataset.get_cell(rows[0]["cell_id"])
    assert "elevation_m" in cell.quality["missing_nonfinite_fields"]
