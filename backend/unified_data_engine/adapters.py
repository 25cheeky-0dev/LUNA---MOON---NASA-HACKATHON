"""Known package-layout adapters; source files and producer code remain untouched."""

import json

from .errors import DatasetError
from .schemas import DatasetManifest


def read_json(path):
    return json.loads(path.read_bytes())


def site04_v3(root, dataset_id=None):
    """Adapt the frozen baseline plus V3 provenance, without regenerating cells."""
    metadata = read_json(root / "baseline/grid_metadata.json")
    tiles = read_json(root / "tile_manifest.json")
    if metadata["grid_version"] != "2.0.0" or tiles["tile_processing_version"] != "3.0.0":
        raise DatasetError(
            "UNSUPPORTED_DATASET_VERSION",
            "The legacy adapter requires baseline 2.0.0 and tile processor 3.0.0",
        )
    crs = metadata["crs"]
    if (
        crs["body"] != "Moon"
        or crs["frame"] != "MOON_ME / DE421"
        or crs["longitude_convention"] != "east-positive [-180,180)"
        or crs["latitude_convention"] != "planetocentric latitude in degrees (on source sphere)"
    ):
        raise DatasetError("UNSUPPORTED_COORDINATES", "Unrecognized legacy coordinate conventions")
    hashes = read_json(root / "SHA256_MANIFEST.json")["files"]
    return DatasetManifest.model_validate(
        dict(
            schema_version="1.0",
            dataset_id=dataset_id or metadata["grid_configuration_id"],
            dataset_version=tiles["tile_processing_version"],
            files_sha256=hashes,
            attributes=dict(
                adapter="site04-v3",
                grid_version=metadata["grid_version"],
                tile_manifest=tiles,
                original_grid_metadata=metadata,
            ),
            tiles=[
                dict(
                    tile_id=metadata["grid_configuration_id"],
                    grid="baseline/grid.parquet",
                    geometry="baseline/grid_geometry.parquet",
                    neighbors="baseline/neighbors.parquet",
                    metadata="baseline/grid_metadata.json",
                    cell_count=metadata["grid"]["cells"],
                    source=metadata["source"],
                    coordinates=dict(
                        frame=crs["frame"],
                        crs_wkt=crs["wkt"],
                        radius_m=crs["radius_m"],
                        latitude_type="planetocentric",
                        longitude_convention="east_signed",
                        vertical_reference=crs["vertical_reference"],
                        frame_evidence_url=metadata["source"]["documentation"],
                    ),
                    columns=dict(latitude="latitude", longitude="longitude", valid="valid"),
                )
            ],
        )
    )


def load_manifest(root, adapter, dataset_id=None):
    if adapter == "site04-v3":
        return site04_v3(root, dataset_id)
    if adapter == "manifest-v1":
        payload = read_json(root / "dataset_manifest.json")
        if payload.get("schema_version") != "1.0":
            raise DatasetError(
                "UNSUPPORTED_SCHEMA_VERSION", "Dataset interface schema_version must be 1.0"
            )
        manifest = DatasetManifest.model_validate(payload)
        if dataset_id is not None and manifest.dataset_id != dataset_id:
            raise DatasetError("DATASET_ID_MISMATCH", "Registry ID differs from dataset manifest")
        return manifest
    raise DatasetError("UNSUPPORTED_ADAPTER", "Unknown dataset adapter")
