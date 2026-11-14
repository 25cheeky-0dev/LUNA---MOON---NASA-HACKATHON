"""Independent Parquet, geometry, projection, topology and integrity validation."""

import hashlib
import json
import math
import re
import threading
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from .adapters import load_manifest, read_json
from .coordinates import CoordinateAdapter, finite
from .errors import DatasetError
from .schemas import CellResult

DEFAULT_COLUMNS = dict(
    cell_id="cell_id",
    latitude="latitude",
    longitude="longitude",
    x="x_m",
    y="y_m",
    elevation="elevation_m",
    slope="slope_deg",
    roughness="roughness_m",
    valid="valid",
    geometry="geometry_wkb",
    neighbor="neighbor_id",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or Path(relative).is_absolute():
        raise DatasetError("UNSAFE_DATASET_PATH", "Dataset asset escapes its registered root")
    return path


def json_safe(value, missing=None, prefix=""):
    """Preserve source values; nonfinite numbers become null with an explicit field list."""
    if isinstance(value, float) and not math.isfinite(value):
        if missing is not None:
            missing.append(prefix)
        return None
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, dict):
        return {
            key: json_safe(item, missing, f"{prefix}.{key}".strip("."))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item, missing, f"{prefix}[{i}]") for i, item in enumerate(value)]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise DatasetError(
        "UNSUPPORTED_FIELD_TYPE", "A source field cannot be represented losslessly in JSON"
    )


class LunarDataset(Protocol):
    """Stable loader boundary, independent of grid generation and layout adapters."""

    def describe(self) -> dict: ...
    def get_cell(self, cell_id: str) -> CellResult: ...
    def list_cell_ids(self, offset: int = 0, limit: int = 100) -> list[str]: ...


class ParquetDataset:
    def __init__(
        self,
        root,
        *,
        adapter="manifest-v1",
        dataset_id=None,
        max_cells=1000000,
        max_tiles=10000,
        cached_tiles=4,
    ):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise DatasetError(
                "DATASET_UNAVAILABLE", "Registered dataset directory is unavailable", 503
            )
        self.max_cells, self.max_tiles, self.cached_tiles = max_cells, max_tiles, cached_tiles
        if min(max_cells, max_tiles, cached_tiles) < 1:
            raise DatasetError(
                "INVALID_RESOURCE_BUDGET", "Dataset resource budgets must be positive"
            )
        self._lock, self._cache = threading.RLock(), OrderedDict()
        self.integrity, self.index, self._neighbors = {}, {}, {}
        self._supplement, self._tile_metadata = {}, {}
        self.max_roundtrip_error_m = 0.0
        self._fingerprints = {}
        try:
            from pyarrow import ArrowException
            from pyproj.exceptions import ProjError
            from shapely.errors import ShapelyError
        except ImportError as exc:
            raise DatasetError(
                "DEPENDENCY_UNAVAILABLE", "Install the backend unified extra to read datasets", 503
            ) from exc
        try:
            self.manifest = load_manifest(self.root, adapter, dataset_id)
            self.snapshot_sha256 = hashlib.sha256(
                self.manifest.model_dump_json().encode()
            ).hexdigest()
            if (
                len(self.manifest.tiles) > max_tiles
                or sum(t.cell_count for t in self.manifest.tiles) > max_cells
            ):
                raise DatasetError(
                    "DATASET_BUDGET_EXCEEDED",
                    "Declared dataset exceeds configured ingestion budget",
                )
            ids = [tile.tile_id for tile in self.manifest.tiles]
            if len(set(ids)) != len(ids):
                raise DatasetError("DUPLICATE_TILE_ID", "Partition IDs must be unique")
            self.tiles = {tile.tile_id: tile for tile in self.manifest.tiles}
            entrypoint = "tile_manifest.json" if adapter == "site04-v3" else "dataset_manifest.json"
            self.manifest_sha256 = sha256_file(self.root / entrypoint)
            for tile in self.manifest.tiles:
                for relative in (tile.grid, tile.geometry, tile.neighbors, tile.metadata):
                    self._verify(relative)
                source = safe_path(self.root, tile.source.filename)
                if source.exists():
                    actual = sha256_file(source)
                    if actual != tile.source.sha256:
                        raise DatasetError(
                            "SOURCE_HASH_MISMATCH",
                            "Source raster checksum differs from its provenance",
                        )
                    self.integrity[tile.source.filename] = dict(
                        sha256=actual, status="HASH_VERIFIED"
                    )
                else:
                    self.integrity[tile.source.filename] = dict(
                        sha256=tile.source.sha256, status="NOT_BUNDLED_OR_UNAVAILABLE"
                    )
                data = self._partition(tile.tile_id)
                for cell_id in data["grid"]:
                    if cell_id in self.index:
                        raise DatasetError(
                            "DUPLICATE_CELL_ID",
                            "Cell IDs must be globally unique across partitions",
                        )
                    self.index[cell_id] = tile.tile_id
                self._neighbors.update(data["neighbors"])
            self._validate_topology()
            if adapter == "site04-v3":
                self._load_v3_provenance()
        except DatasetError:
            raise
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            OverflowError,
            ProjError,
            ShapelyError,
            ArrowException,
        ) as exc:
            raise DatasetError(
                "INVALID_DATASET", f"Dataset ingestion failed ({type(exc).__name__})"
            ) from exc

    def _verify(self, relative):
        path = safe_path(self.root, relative)
        expected = self.manifest.files_sha256.get(relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise DatasetError(
                "MISSING_CHECKSUM", "Every ingested asset requires a declared SHA-256"
            )
        if not path.is_file():
            raise DatasetError(
                "DATASET_UNAVAILABLE", f"Required dataset asset unavailable: {relative}", 503
            )
        actual = sha256_file(path)
        if actual != expected:
            raise DatasetError("CHECKSUM_MISMATCH", f"Dataset asset checksum mismatch: {relative}")
        stat = path.stat()
        self._fingerprints[relative] = (stat.st_size, stat.st_mtime_ns)
        self.integrity[relative] = dict(sha256=actual, status="HASH_VERIFIED")
        return path

    def _read_table(self, relative, tile):
        import pyarrow.parquet as pq
        from pyproj import CRS

        table = pq.read_table(self._verify(relative))
        schema_metadata = {
            key.decode(): value.decode() for key, value in (table.schema.metadata or {}).items()
        }
        for key, expected in (
            ("body", "Moon"),
            ("frame", tile.coordinates.frame),
            ("source_sha256", tile.source.sha256),
        ):
            if key in schema_metadata and schema_metadata[key] != expected:
                raise DatasetError(
                    "PARQUET_METADATA_MISMATCH", f"Parquet {key} conflicts with dataset metadata"
                )
        if "crs_wkt" in schema_metadata and not CRS.from_wkt(schema_metadata["crs_wkt"]).equals(
            CRS.from_wkt(tile.coordinates.crs_wkt)
        ):
            raise DatasetError(
                "PARQUET_METADATA_MISMATCH", "Parquet CRS differs from its declared partition CRS"
            )
        return table.to_pylist(), schema_metadata

    @staticmethod
    def _keyed(rows, column):
        keyed = {}
        for row in rows:
            cell_id = row[column]
            if not isinstance(cell_id, str) or not cell_id or cell_id in keyed:
                raise DatasetError(
                    "DUPLICATE_OR_INVALID_ID", "Cell IDs must be nonempty unique strings"
                )
            keyed[cell_id] = row
        return keyed

    def _partition(self, tile_id):
        from shapely import from_wkb
        from shapely.geometry import Point

        with self._lock:
            tile = self.tiles[tile_id]
            for relative in (tile.grid, tile.geometry, tile.neighbors, tile.metadata):
                try:
                    stat = safe_path(self.root, relative).stat()
                except OSError as exc:
                    raise DatasetError(
                        "DATASET_UNAVAILABLE",
                        "A validated dataset asset is no longer available",
                        503,
                    ) from exc
                if (stat.st_size, stat.st_mtime_ns) != self._fingerprints[relative]:
                    raise DatasetError(
                        "DATASET_CHANGED",
                        "Dataset assets changed; reopen the dataset snapshot",
                        409,
                    )
            if tile_id in self._cache:
                self._cache.move_to_end(tile_id)
                return self._cache[tile_id]
            columns = DEFAULT_COLUMNS | tile.columns
            rows, grid_schema = self._read_table(tile.grid, tile)
            geometries, geometry_schema = self._read_table(tile.geometry, tile)
            links, neighbor_schema = self._read_table(tile.neighbors, tile)
            grid = self._keyed(rows, columns["cell_id"])
            geometry = self._keyed(geometries, columns["cell_id"])
            if len(grid) != tile.cell_count or set(grid) != set(geometry):
                raise DatasetError(
                    "CELL_SET_MISMATCH", "Grid/geometry cell sets or declared row counts differ"
                )
            adapter = CoordinateAdapter(tile.coordinates)
            polygons, neighbors = {}, {cell_id: [] for cell_id in grid}
            for cell_id, row in grid.items():
                values = {
                    name: row[columns[name]]
                    for name in (
                        "latitude",
                        "longitude",
                        "x",
                        "y",
                        "elevation",
                        "slope",
                        "roughness",
                        "valid",
                    )
                }
                if not isinstance(values["valid"], bool):
                    raise DatasetError(
                        "INVALID_VALIDITY_FLAG", "Source validity flag must be boolean"
                    )
                self.max_roundtrip_error_m = max(
                    self.max_roundtrip_error_m,
                    adapter.validate(
                        values["latitude"], values["longitude"], values["x"], values["y"]
                    ),
                )
                if values["valid"] and not all(
                    finite(values[n]) for n in ("elevation", "slope", "roughness")
                ):
                    raise DatasetError(
                        "INVALID_TERRAIN",
                        "Valid terrain cells require finite elevation/slope/roughness",
                    )
                if (
                    finite(values["slope"])
                    and not 0 <= values["slope"] <= 90
                    or finite(values["roughness"])
                    and values["roughness"] < 0
                ):
                    raise DatasetError(
                        "INVALID_TERRAIN", "Slope or roughness is outside its physical range"
                    )
                for prefix, measurement in (
                    ("elevation", values["elevation"]),
                    ("slope", values["slope"]),
                ):
                    low, high, spread = (
                        row.get(prefix + "_min_m" if prefix == "elevation" else "slope_min_deg"),
                        row.get(prefix + "_max_m" if prefix == "elevation" else "slope_max_deg"),
                        row.get(prefix + "_std_m" if prefix == "elevation" else "slope_std_deg"),
                    )
                    if (
                        finite(low)
                        and finite(high)
                        and (low > high or finite(measurement) and not low <= measurement <= high)
                    ):
                        raise DatasetError(
                            "INVALID_TERRAIN",
                            "Source terrain mean/minimum/maximum are inconsistent",
                        )
                    if finite(spread) and spread < 0:
                        raise DatasetError(
                            "INVALID_TERRAIN",
                            "Source terrain standard deviation cannot be negative",
                        )
                fraction = row.get("valid_coverage_fraction")
                if fraction is not None and (not finite(fraction) or not 0 <= fraction <= 1):
                    raise DatasetError("INVALID_TERRAIN", "Coverage fraction must lie in [0,1]")
                grow = geometry[cell_id]
                for key in set(row) & set(grow) - {columns["cell_id"]}:
                    if row[key] != grow[key]:
                        raise DatasetError(
                            "GEOMETRY_ATTRIBUTE_MISMATCH",
                            "Duplicated grid/geometry attributes differ",
                        )
                polygon = from_wkb(grow[columns["geometry"]])
                if (
                    polygon.geom_type not in ("Polygon", "MultiPolygon")
                    or not polygon.is_valid
                    or polygon.is_empty
                    or polygon.area <= 0
                ):
                    raise DatasetError(
                        "INVALID_GEOMETRY", "Cell geometry must be a valid nonempty lunar polygon"
                    )
                if not polygon.covers(Point(values["x"], values["y"])):
                    raise DatasetError(
                        "CENTER_OUTSIDE_CELL", "Projected cell center falls outside its polygon"
                    )
                if all(key in row for key in ("xmin_m", "ymin_m", "xmax_m", "ymax_m")):
                    if any(
                        abs(a - b) > 1e-6
                        for a, b in zip(
                            polygon.bounds,
                            [row[k] for k in ("xmin_m", "ymin_m", "xmax_m", "ymax_m")],
                            strict=True,
                        )
                    ):
                        raise DatasetError(
                            "GEOMETRY_BOUNDS_MISMATCH", "Polygon bounds differ from raw cell bounds"
                        )
                polygons[cell_id] = polygon
            seen = set()
            for link in links:
                pair = link[columns["cell_id"]], link[columns["neighbor"]]
                if pair[0] not in grid or pair[0] == pair[1] or pair in seen:
                    raise DatasetError(
                        "INVALID_NEIGHBORS",
                        "Neighbor source, self-edge or duplicate link is invalid",
                    )
                seen.add(pair)
                neighbors[pair[0]].append(link)
            data = dict(
                grid=grid,
                geometry=geometry,
                neighbors=neighbors,
                polygons=polygons,
                adapter=adapter,
                columns=columns,
                schema_metadata=dict(
                    grid=grid_schema, geometry=geometry_schema, neighbors=neighbor_schema
                ),
                raw_metadata=read_json(self._verify(tile.metadata)),
            )
            self._cache[tile_id] = data
            while len(self._cache) > self.cached_tiles:
                self._cache.popitem(last=False)
            return data

    def _validate_topology(self):
        from pyproj import Transformer
        from shapely.ops import transform

        for cell_id, tile_id in self.index.items():
            tile, data = self.tiles[tile_id], self._partition(tile_id)
            columns = data["columns"]
            links = self._neighbors[cell_id]
            actual_ids = {link[columns["neighbor"]] for link in links}
            row = data["grid"][cell_id]
            if (
                "neighbor_ids_json" in row
                and set(json.loads(row["neighbor_ids_json"])) != actual_ids
            ):
                raise DatasetError(
                    "NEIGHBOR_LIST_MISMATCH", "Cell neighbor list differs from neighbors.parquet"
                )
            for link in links:
                other = link[columns["neighbor"]]
                if other not in self.index:
                    raise DatasetError("DANGLING_NEIGHBOR", "Neighbor references an absent cell")
                other_data = self._partition(self.index[other])
                other_column = other_data["columns"]["neighbor"]
                if cell_id not in {r[other_column] for r in self._neighbors[other]}:
                    raise DatasetError(
                        "NONRECIPROCAL_NEIGHBOR", "Neighbor links must be reciprocal"
                    )
                first, second = data["polygons"][cell_id], other_data["polygons"][other]
                if not data["adapter"].crs.equals(other_data["adapter"].crs):
                    transformer = Transformer.from_crs(
                        other_data["adapter"].crs, data["adapter"].crs, always_xy=True
                    )
                    second = transform(transformer.transform, second)
                tolerance = max(first.length, second.length) * 1e-8
                if first.intersection(second).area > tolerance**2:
                    raise DatasetError("OVERLAPPING_NEIGHBORS", "Neighbor polygons overlap in area")
                shared = first.boundary.intersection(second.boundary).length
                if (
                    tile.neighbor_relation == "edge"
                    and shared <= 0
                    or first.distance(second) > tolerance
                ):
                    raise DatasetError(
                        "DISCONNECTED_NEIGHBOR",
                        "Neighbor polygons do not share the declared relation",
                    )
                if "edge_length_m" in link and (
                    not finite(link["edge_length_m"])
                    or abs(shared - link["edge_length_m"]) > max(1e-5, tolerance)
                ):
                    raise DatasetError(
                        "NEIGHBOR_EDGE_MISMATCH",
                        "Declared edge length differs from polygon geometry",
                    )

    def _load_v3_provenance(self):
        from pyproj import CRS

        manifest = self.manifest.attributes["tile_manifest"]
        baseline = self.manifest.tiles[0]
        if manifest["source_sha256"] != baseline.source.sha256:
            raise DatasetError(
                "TILE_PROVENANCE_MISMATCH",
                "Tile manifest source differs from baseline raster provenance",
            )
        self._verify("tile_manifest.json")
        grid_definition = self.manifest.attributes["original_grid_metadata"]["grid"]
        if grid_definition["rows"] * grid_definition["columns"] != len(self.index):
            raise DatasetError(
                "GRID_DIMENSION_MISMATCH", "Declared grid dimensions differ from its cell count"
            )
        baseline_data = self._partition(baseline.tile_id)
        positions = set()
        for cell_id, row in baseline_data["grid"].items():
            position = row["row"], row["column"]
            if (
                position in positions
                or not 0 <= position[0] < grid_definition["rows"]
                or not 0 <= position[1] < grid_definition["columns"]
            ):
                raise DatasetError(
                    "GRID_INDEX_MISMATCH", "Source row/column indices must be unique and in bounds"
                )
            if cell_id != grid_definition["id_format"].format(row=position[0], column=position[1]):
                raise DatasetError(
                    "GRID_ID_MISMATCH", "Existing ID differs from its declared frozen source format"
                )
            if row["grid_version"] != self.manifest.attributes["grid_version"]:
                raise DatasetError(
                    "GRID_VERSION_MISMATCH",
                    "Cell calculation version differs from baseline metadata",
                )
            size = grid_definition["cell_size_m"]
            origin = grid_definition["origin_upper_left_m"]
            expected_x, expected_y = (
                origin[0] + (position[1] + 0.5) * size,
                origin[1] - (position[0] + 0.5) * size,
            )
            if (
                not finite(size)
                or size <= 0
                or abs(row["x_m"] - expected_x) > 1e-6
                or abs(row["y_m"] - expected_y) > 1e-6
            ):
                raise DatasetError(
                    "GRID_ORIGIN_MISMATCH",
                    "Projected centers differ from the declared source origin/resolution",
                )
            if abs(baseline_data["polygons"][cell_id].area - size**2) > 1e-5:
                raise DatasetError(
                    "GRID_AREA_MISMATCH",
                    "Cell polygon area differs from declared source resolution",
                )
            positions.add(position)
        for tile in manifest["tiles"]:
            tile_id = tile["tile_id"]
            # IDs are used as path segments only after the same root containment check.
            meta_path = f"tiles/{tile_id}/tile_metadata.json"
            cells_path = f"tiles/{tile_id}/cells.jsonl"
            meta = read_json(self._verify(meta_path))
            self._tile_metadata[tile_id] = meta
            if not CRS.from_wkt(meta["projected_crs_wkt"]).equals(
                CRS.from_wkt(baseline.coordinates.crs_wkt)
            ):
                raise DatasetError("TILE_PROVENANCE_MISMATCH", "Tile CRS differs from the baseline")
            if (
                meta["source_sha256"] != manifest["source_sha256"]
                or meta["frame"] != "MOON_ME / DE421"
            ):
                raise DatasetError(
                    "TILE_PROVENANCE_MISMATCH", "Tile source/frame differs from its dataset"
                )
            count = 0
            for line in self._verify(cells_path).read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                cell_id = row["cell_id"]
                if (
                    cell_id in self._supplement
                    or cell_id not in self.index
                    or row["tile_id"] != tile_id
                ):
                    raise DatasetError(
                        "TILE_CELL_MISMATCH",
                        "Provenance cell IDs must match the baseline exactly once",
                    )
                original = self._partition(self.index[cell_id])["grid"][cell_id]
                for key in set(original) & set(row):
                    if original[key] != row[key]:
                        raise DatasetError(
                            "TERRAIN_PROVENANCE_MISMATCH",
                            "V3 provenance differs from frozen baseline values",
                        )
                if original["valid"] != row["data_valid"] or set(
                    json.loads(original["neighbor_ids_json"])
                ) != set(row["neighbor_ids"]):
                    raise DatasetError(
                        "TILE_CELL_MISMATCH", "V3 validity or neighbors differ from the baseline"
                    )
                self._supplement[cell_id] = row
                count += 1
            if count != tile["cell_count"] or count != meta["cell_count"]:
                raise DatasetError(
                    "TILE_COUNT_MISMATCH", "Tile row count differs from its metadata"
                )
        if set(self._supplement) != set(self.index):
            raise DatasetError(
                "TILE_CELL_MISMATCH", "V3 provenance does not cover the baseline cell set"
            )

    def describe(self):
        return deepcopy(
            dict(
                contract_version="1.0",
                dataset_id=self.manifest.dataset_id,
                dataset_version=self.manifest.dataset_version,
                cell_count=len(self.index),
                partition_count=len(self.tiles),
                tile_provenance_count=len(self._tile_metadata),
                status="VALIDATED",
                max_projection_roundtrip_error_m=self.max_roundtrip_error_m,
                manifest_sha256=self.manifest_sha256,
                integrity=self.integrity,
                snapshot_sha256=self.snapshot_sha256,
                attributes=self.manifest.attributes,
                validation_scope="Independent file hashes, Parquet rows/metadata, projection, polygons and declared neighbor topology; no DEM terrain recomputation",
            )
        )

    def list_cell_ids(self, offset=0, limit=100):
        if offset < 0 or not 1 <= limit <= 1000:
            raise DatasetError("INVALID_PAGINATION", "Offset must be nonnegative; limit 1–1000")
        return list(self.index)[offset : offset + limit]

    def get_cell(self, cell_id):
        if cell_id not in self.index:
            raise DatasetError(
                "CELL_NOT_FOUND", "Cell ID is not present in the selected dataset", 404
            )
        tile_id = self.index[cell_id]
        tile, data = self.tiles[tile_id], self._partition(tile_id)
        row, columns = data["grid"][cell_id], data["columns"]
        missing = []
        terrain = json_safe(row, missing)
        supplement = self._supplement.get(cell_id)
        source_tile_id = supplement.get("tile_id") if supplement else None
        quality = dict(
            source_valid=row[columns["valid"]],
            missing_nonfinite_fields=missing,
            source_quality=(supplement or {}).get("quality_status", "SEE_DATASET_METADATA"),
            flags=json_safe(supplement or {}),
            dem_height_applied_to_horizons=False,
        )
        return CellResult(
            dataset_id=self.manifest.dataset_id,
            dataset_version=self.manifest.dataset_version,
            partition_id=tile_id,
            cell_id=cell_id,
            terrain=terrain,
            geometry=json_safe(data["geometry"][cell_id]),
            neighbors=json_safe(data["neighbors"][cell_id]),
            source_coordinates={
                name: row[columns[key]]
                for name, key in (
                    ("latitude", "latitude"),
                    ("longitude", "longitude"),
                    ("x_m", "x"),
                    ("y_m", "y"),
                )
            },
            coordinates=tile.coordinates,
            quality=quality,
            provenance=json_safe(
                dict(
                    source=tile.source.model_dump(),
                    metadata=data["raw_metadata"],
                    parquet_schema_metadata=data["schema_metadata"],
                    manifest_sha256=self.manifest_sha256,
                    assets=self.integrity,
                    tile_cell_record=supplement,
                    tile_metadata=self._tile_metadata.get(source_tile_id),
                )
            ),
        )
