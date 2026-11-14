import json
import shutil

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from unified_data_engine.errors import DatasetError
from unified_data_engine.loader import ParquetDataset, sha256_file

from .conftest import V3, write_synthetic


def test_all_actual_v3_tables_and_frozen_cell(dataset):
    assert len(dataset.index) == 400
    assert sum(len(links) for links in dataset._neighbors.values()) == 1520
    cell = dataset.get_cell("SITE04_R000_C000")
    assert cell.terrain["elevation_m"] == 1072.0976434326171
    assert cell.terrain["slope_deg"] == 32.13135594956228
    assert cell.terrain["roughness_m"] == 0.9163221785602584
    assert cell.source_coordinates == dict(
        latitude=-89.7787655990766, longitude=-167.51751061504552, x_m=-1450.0, y_m=-6550.0
    )
    assert cell.provenance["tile_cell_record"]["lola_shot_count"] is None
    assert cell.provenance["tile_cell_record"]["elevation_uncertainty_m"] is None
    assert cell.provenance["tile_metadata"]["frame"] == "MOON_ME / DE421"
    assert cell.terrain["grid_version"] == "2.0.0" and cell.dataset_version == "3.0.0"
    assert dataset.max_roundtrip_error_m < 0.001
    assert cell.quality["dem_height_applied_to_horizons"] is False
    assert (
        cell.provenance["assets"]["baseline/grid.parquet"]["sha256"]
        == "dc32b04162bd3db3e114ba816a1958f1ef918d7f38effa7eaee992ca32fa45e4"
    )


def test_stable_ids_and_isolated_results(dataset):
    ids = dataset.list_cell_ids(0, 1000)
    assert len(ids) == len(set(ids)) == 400
    assert ids[0] == "SITE04_R000_C000" and ids[-1] == "SITE04_R019_C019"
    cell = dataset.get_cell(ids[0])
    cell.terrain["elevation_m"] = -12345
    assert dataset.get_cell(ids[0]).terrain["elevation_m"] == 1072.0976434326171
    with pytest.raises(DatasetError, match="not present"):
        dataset.get_cell("SITE04_R999_C999")


def test_different_test_only_northern_multi_tile_configuration(tmp_path):
    write_synthetic(tmp_path)
    dataset = ParquetDataset(tmp_path)
    assert len(dataset.index) == 12 and len(dataset.tiles) == 2
    assert dataset.manifest.dataset_version == "test-only-9.0"
    cell = dataset.get_cell("TEST_ONLY:T1:R1:C2")
    assert cell.source_coordinates["latitude"] > 0
    assert cell.terrain["elevation_m"] == 113
    assert cell.coordinates.longitude_convention == "east_signed"
    assert cell.provenance["source"]["url"].endswith("SYNTHETIC_TEST_ONLY")


def change_table(root, relative, change):
    table = pq.read_table(root / relative)
    rows = table.to_pylist()
    change(rows)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), root / relative)
    path = root / "SHA256_MANIFEST.json"
    manifest = json.loads(path.read_bytes())
    manifest["files"][relative] = sha256_file(root / relative)
    path.write_bytes(json.dumps(manifest).encode())


@pytest.mark.parametrize(
    "corruption", ["duplicate_id", "coordinate", "geometry", "neighbor", "terrain", "validity"]
)
def test_independent_checks_beyond_declared_hashes(tmp_path, corruption):
    shutil.copytree(V3, tmp_path, dirs_exist_ok=True)
    if corruption == "duplicate_id":
        change_table(
            tmp_path,
            "baseline/grid.parquet",
            lambda rows: rows[1].update(cell_id=rows[0]["cell_id"]),
        )
    elif corruption == "coordinate":
        change_table(tmp_path, "baseline/grid.parquet", lambda rows: rows[0].update(latitude=-80.0))
    elif corruption == "geometry":
        change_table(
            tmp_path,
            "baseline/grid_geometry.parquet",
            lambda rows: rows[0].update(geometry_wkb=rows[1]["geometry_wkb"]),
        )
    elif corruption == "neighbor":
        change_table(
            tmp_path,
            "baseline/neighbors.parquet",
            lambda rows: rows[0].update(neighbor_id="ABSENT"),
        )
    elif corruption == "terrain":
        change_table(tmp_path, "baseline/grid.parquet", lambda rows: rows[0].update(roughness_m=-1))
    else:
        change_table(
            tmp_path, "baseline/grid.parquet", lambda rows: rows[0].update(slope_deg=float("nan"))
        )
    with pytest.raises(DatasetError):
        ParquetDataset(tmp_path, adapter="site04-v3")


def test_checksum_and_unavailable_dataset(tmp_path):
    with pytest.raises(DatasetError) as unavailable:
        ParquetDataset(tmp_path / "missing")
    assert unavailable.value.status == 503
    shutil.copytree(V3, tmp_path, dirs_exist_ok=True)
    (tmp_path / "baseline/grid.parquet").write_bytes(b"corrupted test-only bytes")
    with pytest.raises(DatasetError) as corrupted:
        ParquetDataset(tmp_path, adapter="site04-v3")
    assert corrupted.value.code == "CHECKSUM_MISMATCH"


@pytest.mark.parametrize(
    "modification", ["schema", "path", "frame", "longitude", "earth", "count", "budget"]
)
def test_unsupported_or_unsafe_contracts(tmp_path, modification):
    manifest = write_synthetic(tmp_path)
    if modification == "schema":
        manifest["schema_version"] = "99.0"
    elif modification == "path":
        manifest["tiles"][0]["grid"] = "../escape.parquet"
    elif modification == "frame":
        manifest["tiles"][0]["coordinates"]["frame"] = "MOON_PA"
    elif modification == "longitude":
        manifest["tiles"][0]["coordinates"]["longitude_convention"] = "west_positive"
    elif modification == "earth":
        manifest["tiles"][0]["coordinates"]["radius_m"] = 6378137
    elif modification == "count":
        manifest["tiles"][0]["cell_count"] = 5
    else:
        manifest["tiles"][0]["cell_count"] = 1000001
    (tmp_path / "dataset_manifest.json").write_bytes(json.dumps(manifest).encode())
    with pytest.raises(DatasetError):
        ParquetDataset(tmp_path)


def test_modified_snapshot_refused(tmp_path):
    write_synthetic(tmp_path)
    dataset = ParquetDataset(tmp_path)
    path = tmp_path / "tile0-grid.parquet"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(DatasetError) as error:
        dataset.get_cell("TEST_ONLY:T0:R0:C0")
    assert error.value.code == "DATASET_CHANGED"


def test_source_generation_version_not_silently_accepted(tmp_path):
    shutil.copytree(V3, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "tile_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["tile_processing_version"] = "4.0.0"
    path.write_bytes(json.dumps(manifest).encode())
    with pytest.raises(DatasetError) as error:
        ParquetDataset(tmp_path, adapter="site04-v3")
    assert error.value.code == "UNSUPPORTED_DATASET_VERSION"
