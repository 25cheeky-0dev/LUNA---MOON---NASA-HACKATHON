"""Selected-cell terrain/celestial joins with explicit scientific boundaries."""

from pydantic import ValidationError

from celestial_engine.celestial_service import CelestialService
from celestial_engine.horizons_client import HorizonsClient

from .coordinates import CoordinateAdapter
from .errors import DatasetError
from .schemas import CombinedResult
from .terrain_bridge import TerrainBridge
from .vectors import TerrainVectors
from .visibility import visibility


class UnifiedDataService:
    def __init__(self, registry, celestial=None):
        self.registry, self.celestial = registry, celestial or CelestialService()
        self._vectors = {}
        self.terrain = TerrainBridge()

    def vectors(self, dataset_id):
        dataset = self.registry.get(dataset_id)
        with self.registry.lock:
            if dataset_id not in self._vectors:
                self._vectors[dataset_id] = TerrainVectors(dataset)
            return self._vectors[dataset_id]

    def analyze(self, dataset_id, cell_id, request):
        dataset = self.registry.get(dataset_id)
        cell = dataset.get_cell(cell_id)
        if not cell.quality["source_valid"]:
            raise DatasetError(
                "CELL_INVALID", "Source marks this terrain cell invalid; celestial join refused"
            )
        source = cell.source_coordinates
        adapter = CoordinateAdapter(cell.coordinates)
        latitude, longitude = adapter.to_horizons(source["latitude"], source["longitude"])
        try:
            query = request.at(latitude, longitude)
        except ValidationError as exc:
            raise DatasetError(
                "INVALID_REQUEST", "Invalid UTC interval, step or Horizons altitude"
            ) from exc
        engine = self.celestial
        if request.verified_cache_only:
            engine = CelestialService(HorizonsClient(engine.client.cache.root, offline=True))
        ephemeris = engine.ephemeris(query)
        if [row.timestamp_utc for row in ephemeris.records] != query.timestamps():
            raise DatasetError(
                "TIMESTAMP_MISMATCH",
                "Celestial result does not preserve the selected UTC cadence",
                503,
            )
        if any(
            row.latitude_deg != latitude
            or row.longitude_east_deg != longitude
            or row.altitude_km != query.altitude_km
            for row in ephemeris.records
        ):
            raise DatasetError(
                "OBSERVER_MISMATCH", "Celestial result observer differs from the selected cell", 503
            )
        terrain_profile = self.terrain.profile(dataset, cell, request)
        return CombinedResult(
            cell=cell,
            terrain_vector=self.vectors(dataset_id).get(cell_id),
            observer=dict(
                latitude_deg=latitude,
                longitude_east_deg=longitude,
                altitude_km=query.altitude_km,
                altitude_reference=query.altitude_reference,
                grid_elevation_applied=False,
                source_longitude_unchanged=source["longitude"],
                latitude_conversion="identity: planetocentric equals planetodetic on declared sphere",
                vertical_reference_status="DEM_TO_HORIZONS_NOT_RECONCILED",
            ),
            ephemeris=ephemeris,
            visibility=visibility(ephemeris, request, terrain_profile),
            quality=dict(
                terrain_source_valid=cell.quality["source_valid"],
                terrain_source_quality=cell.quality["source_quality"],
                celestial_data_quality=ephemeris.metadata["data_quality"],
                missing_observations=ephemeris.metadata["missing_observations"],
                terrain_obstruction="NOT_CALCULATED",
                landing_eligibility="NOT_ASSESSED",
            ),
            provenance=dict(
                dataset_manifest_sha256=dataset.manifest_sha256,
                dataset_snapshot_sha256=dataset.snapshot_sha256,
                terrain=cell.provenance,
                celestial=ephemeris.metadata,
                join_keys=dict(dataset_id=dataset_id, cell_id=cell_id, timestamps="timestamp_utc"),
                join_method="exact selected geographic center and requested UTC timestamps",
            ),
            limitations=[
                "Research prototype; not mission-certified",
                "DEM elevation is a terrain measurement, not the Horizons observer altitude",
                "Source interpolation and missing uncertainty/count flags remain authoritative",
                "Apparent target-center angles do not establish terrain clearance, sunlight, power or communications",
                "The real geographic foundation is the frozen V3 package; no full-Moon coverage is claimed",
            ],
        )
