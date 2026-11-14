"""Read-only selected-cell adapter to the existing finite-DEM horizon provider."""

import math
import threading
from collections import OrderedDict
from copy import deepcopy

from .loader import safe_path, sha256_file


class TerrainBridge:
    def __init__(self):
        self.cache, self.lock = OrderedDict(), threading.RLock()

    def profile(self, dataset, cell, request):
        source = cell.provenance["source"]
        path = safe_path(dataset.root, source["filename"])
        if not path.is_file():
            return dict(
                coverage="UNAVAILABLE",
                far_field_complete=False,
                reason="Original source raster is not available in this dataset root",
                source=source,
                visibility="UNKNOWN",
            )
        key = (
            dataset.manifest_sha256,
            cell.cell_id,
            source["sha256"],
            path.stat().st_mtime_ns,
            request.observer_height_above_dem_m,
            request.terrain_azimuth_step_deg,
        )
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return deepcopy(self.cache[key])
            try:
                import rasterio
                from pyproj import CRS

                from app.providers import terrain

                if sha256_file(path) != source["sha256"]:
                    raise terrain.TerrainUnavailable(
                        "Source DEM hash no longer matches its provenance"
                    )
                coordinates = cell.source_coordinates
                point = dict(lat_deg=coordinates["latitude"], lon_east_deg=coordinates["longitude"])

                def load_point():
                    raster = rasterio.open(path)
                    try:
                        if not CRS.from_user_input(raster.crs).equals(
                            CRS.from_wkt(cell.coordinates.crs_wkt)
                        ):
                            raise terrain.TerrainUnavailable(
                                "Source raster CRS differs from the validated grid"
                            )
                        if abs(raster.transform.b) > 1e-9 or abs(raster.transform.d) > 1e-9:
                            raise terrain.TerrainUnavailable("Rotated source raster is unsupported")
                        if not (
                            raster.bounds.left <= coordinates["x_m"] < raster.bounds.right
                            and raster.bounds.bottom < coordinates["y_m"] <= raster.bounds.top
                        ):
                            raise terrain.TerrainUnavailable(
                                "Cell center is outside the source raster"
                            )
                        return (
                            raster,
                            source,
                            coordinates["x_m"],
                            coordinates["y_m"],
                            source["sha256"],
                        )
                    except Exception:
                        raster.close()
                        raise

                result = terrain.horizon(
                    None,
                    request.observer_height_above_dem_m,
                    request.terrain_azimuth_step_deg,
                    observer_site=point,
                    raster_loader=load_point,
                )
                result.update(
                    coverage="PARTIAL",
                    far_field_complete=False,
                    source=source,
                    observing_point=point,
                    observing_point_xy_m=[coordinates["x_m"], coordinates["y_m"]],
                    reference_alignment="DEM_TO_HORIZONS_NOT_RECONCILED",
                    visibility="UNKNOWN",
                )
                if not all(
                    sample["terrain_horizon_elevation_deg"] is None
                    or math.isfinite(sample["terrain_horizon_elevation_deg"])
                    for sample in result["azimuth_samples"]
                ):
                    raise terrain.TerrainUnavailable("Nonfinite terrain horizon")
            except ImportError:
                result = dict(
                    coverage="UNAVAILABLE",
                    far_field_complete=False,
                    reason="Install the terrain extra for source-raster horizon sampling",
                    source=source,
                    visibility="UNKNOWN",
                )
            except (OSError, ValueError, RuntimeError) as exc:
                result = dict(
                    coverage="UNAVAILABLE",
                    far_field_complete=False,
                    reason=f"Raster horizon could not be validated ({type(exc).__name__})",
                    source=source,
                    visibility="UNKNOWN",
                )
            except terrain.TerrainUnavailable as exc:
                result = dict(
                    coverage="UNAVAILABLE",
                    far_field_complete=False,
                    reason=str(exc),
                    source=source,
                    visibility="UNKNOWN",
                )
            self.cache[key] = result
            while len(self.cache) > 16:
                self.cache.popitem(last=False)
            return deepcopy(result)
