"""Reproduce Site04 checksum, skyline, convergence and recorded-NASA evidence."""

import argparse
import json
import platform
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyproj
import rasterio

from app.providers.horizon_comparison import compare_ephemeris
from app.providers.terrain_horizon import TerrainHorizonEngine, file_sha256
from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient, parameters
from celestial_engine.schemas import EphemerisRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--angular-step", type=float, default=1)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")

    started = time.perf_counter()
    engine = TerrainHorizonEngine.from_v3(args.v3_root)
    load_seconds = time.perf_counter() - started
    fine = TerrainHorizonEngine.from_v3(args.v3_root, sample_step_m=1.25)
    manifest = Path(args.v3_root) / "SHA256_MANIFEST.json"
    save(
        "source_validation.json",
        dict(
            source_provenance=engine.provenance,
            raster=engine.raster_metadata,
            manifest_sha256=file_sha256(manifest),
            manifest_expected_dem_sha256=json.loads(manifest.read_text())["files"][
                engine.source_path.name
            ],
            actual_dem_sha256=engine.digest,
            matched=True,
            load_seconds=load_seconds,
            versions=dict(
                python=platform.python_version(),
                numpy=np.__version__,
                rasterio=rasterio.__version__,
                pyproj=pyproj.__version__,
            ),
        ),
    )
    ids = ["SITE04_R000_C000", "SITE04_R000_C001"]
    summaries = []
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, layout="constrained")
    client = HorizonsClient(Path(__file__).parents[1] / "tests/fixtures/unified_nasa", offline=True)
    for cell_id, ax in zip(ids, axes, strict=True):
        started = time.perf_counter()
        result = engine.diagnostic_skyline(cell_id, 1, args.angular_step)
        elapsed = time.perf_counter() - started
        started = time.perf_counter()
        cached = engine.diagnostic_skyline(cell_id, 1, args.angular_step)
        cached_elapsed = time.perf_counter() - started
        assert cached == result
        save(cell_id + ".json", result)
        refined = fine.diagnostic_skyline(cell_id, 1, args.angular_step)
        angles = np.array([r["terrain_horizon_elevation_deg"] for r in result["azimuth_samples"]])
        finer = np.array([r["terrain_horizon_elevation_deg"] for r in refined["azimuth_samples"]])
        difference = finer - angles
        azimuths = [r["azimuth_deg"] for r in result["azimuth_samples"]]
        ax.plot(azimuths, angles, linewidth=1.2, color="#156d91", label="2.5 m samples")
        ax.plot(azimuths, finer, linewidth=0.8, alpha=0.7, color="#d46b25", label="1.25 m check")
        ax.axhline(0, color="#666666", linewidth=0.7)
        ax.set(
            title=cell_id + " | observer 1 m above sampled ground",
            ylabel="Elevation (degrees)",
            xlim=(0, 360),
        )
        ax.grid(alpha=0.2)
        ax.legend(loc="best")
        c = engine.cells[cell_id]
        req = EphemerisRequest(
            latitude_deg=c["latitude_deg"],
            longitude_east_deg=c["longitude_east_deg"],
            altitude_km=0,
            start_utc="2026-11-15T00:00:00Z",
            end_utc="2026-11-22T00:00:00Z",
            step_minutes=60,
        )
        ephemeris = CelestialService(client).ephemeris(req)
        # Three original UTC rows illustrate the join without resampling NASA values.
        subset = ephemeris.model_dump(mode="json")
        subset["records"] = subset["records"][:3]
        raw = {
            body: client.cache.get(parameters(target, req))[0]
            for body, target in (("sun", 10), ("earth", 399))
        }
        comparison = compare_ephemeris(engine, cell_id, 1, subset, raw_sources=raw)
        assert all(
            r["terrain"][b]["state"] == "UNKNOWN"
            for r in comparison["records"]
            for b in ("sun", "earth")
        )
        assert [r["source_observation"] for r in comparison["records"]] == subset["records"]
        save(cell_id + "_horizons_comparison.json", comparison)
        summaries.append(
            dict(
                cell_id=cell_id,
                original_center=c,
                observer_ground_height_m=result["observer_ground_height_m"],
                skyline_min_deg=float(angles.min()),
                skyline_max_deg=float(angles.max()),
                supported_radius_min_m=min(
                    r["supported_radius_m"] for r in result["azimuth_samples"]
                ),
                supported_radius_max_m=max(
                    r["supported_radius_m"] for r in result["azimuth_samples"]
                ),
                compute_seconds=elapsed,
                cache_seconds=cached_elapsed,
                sample_step_m=2.5,
                refinement_step_m=1.25,
                refinement_max_increase_deg=float(difference.max()),
                refinement_max_absolute_difference_deg=float(np.max(np.abs(difference))),
                refinement_rms_difference_deg=float(np.sqrt(np.mean(difference**2))),
                refinement_is_error_bound=False,
                vertical_reference_verified=False,
                visibility="UNKNOWN",
                nasa_delivery="VERIFIED_RECORDED_CACHE",
                compatibility_failures=comparison["compatibility_failures"],
            )
        )
    axes[-1].set_xlabel("Geographic azimuth clockwise from north (degrees)")
    fig.suptitle(
        "Site04 local skylines — conditional radial-height interpretation\n"
        "Full 16 km DEM | 1° diagnostic directions | unknown far field and vertical reference",
        fontsize=12,
    )
    fig.savefig(output / "site04_skylines.png", dpi=170)
    plt.close(fig)
    save(
        "validation_summary.json",
        dict(
            cells=summaries,
            angular_step_deg=args.angular_step,
            far_field_complete=False,
            vertical_reference_verified=False,
            only_requested_cells_computed=True,
        ),
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
