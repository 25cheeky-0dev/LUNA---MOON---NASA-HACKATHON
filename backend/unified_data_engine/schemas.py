"""The integration schema version is separate from any grid calculation version."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from celestial_engine.schemas import EphemerisRequest, EphemerisResult


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CoordinateReference(Contract):
    body: Literal["Moon"] = "Moon"
    frame: Literal["MOON_ME / DE421"]
    crs_wkt: str = Field(min_length=1)
    radius_m: float = Field(gt=0)
    latitude_type: Literal["planetocentric", "planetodetic"]
    longitude_convention: Literal["east_signed", "east_0_360"]
    projected_units: Literal["m"] = "m"
    elevation_units: Literal["m"] = "m"
    vertical_reference: str = Field(min_length=1)
    frame_evidence_url: str = Field(min_length=1)


class RasterSource(Contract):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    url: str = Field(pattern=r"^https://")
    documentation: str = Field(pattern=r"^https://")


class TileSpec(Contract):
    tile_id: str = Field(min_length=1)
    grid: str
    geometry: str
    neighbors: str
    metadata: str
    cell_count: int = Field(gt=0)
    coordinates: CoordinateReference
    source: RasterSource
    columns: dict[str, str] = Field(default_factory=dict)
    neighbor_relation: Literal["edge", "touch"] = "edge"


class DatasetManifest(Contract):
    schema_version: Literal["1.0"]
    dataset_id: str = Field(min_length=1, max_length=128)
    dataset_version: str = Field(min_length=1)
    tiles: list[TileSpec] = Field(min_length=1)
    files_sha256: dict[str, str]
    # Descriptive attributes survive without being interpreted as compatibility claims.
    attributes: dict = Field(default_factory=dict)


class AnalysisRequest(Contract):
    start_utc: str
    end_utc: str
    step_minutes: int = Field(default=60, strict=True, ge=1, le=1440)
    horizons_altitude_km: float = Field(default=0, ge=-10, le=100)
    altitude_reference: Literal["horizons_lunar_reference"] = "horizons_lunar_reference"
    verified_cache_only: StrictBool = False
    observer_height_above_dem_m: float = Field(default=1, ge=0, le=100)
    terrain_azimuth_step_deg: int = Field(default=10, strict=True, ge=5, le=30)
    min_shared_window_minutes: float = Field(default=180, gt=0, le=44640)

    @model_validator(mode="after")
    def validate_interval(self):
        self.at(0, 0)
        return self

    def at(self, latitude, longitude):
        return EphemerisRequest(
            latitude_deg=latitude,
            longitude_east_deg=longitude,
            altitude_km=self.horizons_altitude_km,
            altitude_reference=self.altitude_reference,
            start_utc=self.start_utc,
            end_utc=self.end_utc,
            step_minutes=self.step_minutes,
        )


class CellResult(Contract):
    contract_version: Literal["1.0"] = "1.0"
    dataset_id: str
    dataset_version: str
    partition_id: str
    cell_id: str
    terrain: dict
    geometry: dict
    neighbors: list[dict]
    source_coordinates: dict
    coordinates: CoordinateReference
    quality: dict
    provenance: dict


class CombinedResult(Contract):
    contract_version: Literal["1.0"] = "1.0"
    cell: CellResult
    terrain_vector: dict
    observer: dict
    ephemeris: EphemerisResult
    quality: dict
    provenance: dict
    visibility: dict
    limitations: list[str]
