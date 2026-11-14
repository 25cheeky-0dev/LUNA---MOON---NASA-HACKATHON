"""Validate a package and write a selected-cell combined NASA response."""

import argparse
from pathlib import Path

from celestial_engine.cache import atomic_write
from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient

from .registry import DatasetRegistry
from .schemas import AnalysisRequest
from .service import UnifiedDataService
from .vectors import export_vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--adapter", choices=["site04-v3", "manifest-v1"], default="manifest-v1")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--start-utc", required=True)
    parser.add_argument("--end-utc", required=True)
    parser.add_argument("--step-minutes", type=int, default=60)
    parser.add_argument("--horizons-altitude-km", type=float, default=0)
    parser.add_argument("--cache-dir", default="data/celestial")
    parser.add_argument("--verified-cache-only", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    registry = DatasetRegistry(
        [dict(dataset_id=args.dataset_id, root=args.root, adapter=args.adapter)]
    )
    engine = UnifiedDataService(registry, CelestialService(HorizonsClient(args.cache_dir)))
    request = AnalysisRequest(
        start_utc=args.start_utc,
        end_utc=args.end_utc,
        step_minutes=args.step_minutes,
        horizons_altitude_km=args.horizons_altitude_km,
        verified_cache_only=args.verified_cache_only,
    )
    result = engine.analyze(args.dataset_id, args.cell_id, request)
    atomic_write(Path(args.output), result.model_dump_json(indent=2).encode())
    export_vectors(engine.vectors(args.dataset_id), Path(args.output).parent)
    print(
        f"Validated {registry.get(args.dataset_id).describe()['cell_count']} cells; exported {len(result.ephemeris.records)} observations"
    )


if __name__ == "__main__":
    main()
