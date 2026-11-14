import json
from pathlib import Path

import pytest

from unified_data_engine.loader import ParquetDataset
from unified_data_engine.registry import DatasetRegistry

FIXTURES = Path(__file__).parents[1] / "fixtures"
V3 = FIXTURES / "site04-v3"


@pytest.fixture(scope="session")
def dataset():
    return ParquetDataset(V3, adapter="site04-v3", dataset_id="site04-v3")


@pytest.fixture
def registry(dataset):
    result = DatasetRegistry([dict(dataset_id="site04-v3", root=str(V3), adapter="site04-v3")])
    result.loaded["site04-v3"] = dataset
    return result


def write_synthetic(
    root, *, tile_count=2, rows=2, columns=3, size=250, north=True, version="test-only-9.0"
):
    """TEST ONLY: a different projection, dimensions, scale and ID scheme from Site04."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pyproj import CRS, Transformer
    from shapely.geometry import box

    from unified_data_engine.loader import sha256_file

    root.mkdir(parents=True, exist_ok=True)
    crs = CRS.from_proj4(
        f"+proj=stere +lat_0={90 if north else -90} +lat_ts={90 if north else -90} +lon_0=30 +R=1737400 +units=m +no_defs"
    )
    inverse = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
    source = dict(
        filename="unavailable-test-source.tif",
        sha256="0" * 64,
        url="https://example.invalid/SYNTHETIC_TEST_ONLY",
        documentation="https://example.invalid/SYNTHETIC_TEST_ONLY",
    )
    tiles, hashes = [], {}
    for tile in range(tile_count):
        grid, geometry, neighbors = [], [], []
        ids = {(r, c): f"TEST_ONLY:T{tile}:R{r}:C{c}" for r in range(rows) for c in range(columns)}
        for r in range(rows):
            for c in range(columns):
                left, bottom = (tile * columns + c) * size, 10000 + r * size
                x, y = left + size / 2, bottom + size / 2
                lon, lat = inverse.transform(x, y)
                cell_id = ids[r, c]
                grid.append(
                    dict(
                        cell_id=cell_id,
                        latitude=lat,
                        longitude=lon,
                        x_m=x,
                        y_m=y,
                        elevation_m=float(100 + tile * 10 + r + c),
                        slope_deg=float(2 + r),
                        roughness_m=0.5 + c,
                        valid=True,
                    )
                )
                geometry.append(
                    dict(
                        cell_id=cell_id,
                        geometry_wkb=box(left, bottom, left + size, bottom + size).wkb,
                    )
                )
                for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    if (r + dr, c + dc) in ids:
                        neighbors.append(
                            dict(
                                cell_id=cell_id,
                                neighbor_id=ids[r + dr, c + dc],
                                edge_length_m=float(size),
                            )
                        )
        files = {
            "grid": f"tile{tile}-grid.parquet",
            "geometry": f"tile{tile}-geometry.parquet",
            "neighbors": f"tile{tile}-neighbors.parquet",
            "metadata": f"tile{tile}-metadata.json",
        }
        for name, records in (("grid", grid), ("geometry", geometry), ("neighbors", neighbors)):
            pq.write_table(pa.Table.from_pylist(records), root / files[name])
        (root / files["metadata"]).write_text(
            json.dumps(dict(label="SYNTHETIC_TEST_ONLY", rows=rows, columns=columns)),
            encoding="utf-8",
        )
        for relative in files.values():
            hashes[relative] = sha256_file(root / relative)
        tiles.append(
            dict(
                tile_id=f"TEST_ONLY_TILE_{tile}",
                cell_count=rows * columns,
                **files,
                source=source,
                coordinates=dict(
                    frame="MOON_ME / DE421",
                    crs_wkt=crs.to_wkt(),
                    radius_m=1737400,
                    latitude_type="planetocentric",
                    longitude_convention="east_signed",
                    vertical_reference="SYNTHETIC_TEST_ONLY",
                    frame_evidence_url="https://example.invalid/SYNTHETIC_TEST_ONLY",
                ),
            )
        )
    manifest = dict(
        schema_version="1.0",
        dataset_id="synthetic-test-only",
        dataset_version=version,
        tiles=tiles,
        files_sha256=hashes,
        attributes=dict(synthetic_test_only=True),
    )
    (root / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest
