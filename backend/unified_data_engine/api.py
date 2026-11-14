"""Additive v1 data endpoints, with dependency-injectable registry and engine."""

from functools import lru_cache

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import Field

from celestial_engine.data_validation import EphemerisError
from celestial_engine.horizons_client import SourceUnavailable

from .comparisons import ComparisonRequest, compare
from .errors import DatasetError
from .registry import DatasetRegistry
from .schemas import AnalysisRequest, CellResult, CombinedResult
from .service import UnifiedDataService

router = APIRouter(prefix="/api/v1/data", tags=["unified-data"])


@lru_cache(maxsize=1)
def get_service():
    return UnifiedDataService(DatasetRegistry.from_environment())


class CellAnalysisRequest(AnalysisRequest):
    cell_id: str = Field(min_length=1, max_length=512)


def dataset_error(exc):
    return JSONResponse(
        status_code=exc.status,
        content=dict(
            contract_version="1.0", error_code=exc.code, detail=exc.detail, fallback="NONE"
        ),
    )


@router.get("/datasets")
def discover(service: UnifiedDataService = Depends(get_service)):
    return service.registry.discover()


@router.get("/datasets/{dataset_id}")
def inspect_dataset(dataset_id: str, service: UnifiedDataService = Depends(get_service)):
    try:
        return service.registry.get(dataset_id).describe()
    except DatasetError as exc:
        return dataset_error(exc)


@router.get("/datasets/{dataset_id}/cells")
def cells(
    dataset_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    elevation_min_m: float | None = Query(None, allow_inf_nan=False),
    elevation_max_m: float | None = Query(None, allow_inf_nan=False),
    slope_max_deg: float | None = Query(None, ge=0, le=90, allow_inf_nan=False),
    roughness_max_m: float | None = Query(None, ge=0, allow_inf_nan=False),
    valid_only: bool = True,
    service: UnifiedDataService = Depends(get_service),
):
    try:
        dataset = service.registry.get(dataset_id)
        if (
            elevation_min_m is not None
            and elevation_max_m is not None
            and elevation_min_m > elevation_max_m
        ):
            raise DatasetError("INVALID_FILTER", "Minimum elevation exceeds maximum elevation")
        return service.vectors(dataset_id).filter(
            offset=offset,
            limit=limit,
            elevation_min_m=elevation_min_m,
            elevation_max_m=elevation_max_m,
            slope_max_deg=slope_max_deg,
            roughness_max_m=roughness_max_m,
            valid_only=valid_only,
        ) | {"dataset_id": dataset.manifest.dataset_id}
    except DatasetError as exc:
        return dataset_error(exc)


@router.get("/datasets/{dataset_id}/cells/{cell_id:path}", response_model=CellResult)
def inspect_cell(dataset_id: str, cell_id: str, service: UnifiedDataService = Depends(get_service)):
    try:
        return service.registry.get(dataset_id).get_cell(cell_id)
    except DatasetError as exc:
        return dataset_error(exc)


@router.get("/datasets/{dataset_id}/vectors/{cell_id:path}")
def vector(dataset_id: str, cell_id: str, service: UnifiedDataService = Depends(get_service)):
    try:
        return service.vectors(dataset_id).get(cell_id)
    except DatasetError as exc:
        return dataset_error(exc)


@router.get("/datasets/{dataset_id}/vectors")
def vector_page(
    dataset_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: UnifiedDataService = Depends(get_service),
):
    try:
        vectors = service.vectors(dataset_id)
        page = vectors.filter(offset=offset, limit=limit)
        return dict(
            contract_version="1.0",
            dataset_id=dataset_id,
            total=page["total"],
            offset=offset,
            limit=limit,
            normalization=vectors.fit,
            vectors=[vectors.get(cell_id) for cell_id in page["cell_ids"]],
        )
    except DatasetError as exc:
        return dataset_error(exc)


@router.get("/datasets/{dataset_id}/similarity")
def similarity(
    dataset_id: str,
    cell_id: str,
    limit: int = Query(10, ge=1, le=100),
    service: UnifiedDataService = Depends(get_service),
):
    try:
        return service.vectors(dataset_id).similar(cell_id, limit=limit)
    except DatasetError as exc:
        return dataset_error(exc)


@router.post("/datasets/{dataset_id}/comparisons")
def comparisons(
    dataset_id: str, request: ComparisonRequest, service: UnifiedDataService = Depends(get_service)
):
    try:
        return compare(service, dataset_id, request)
    except DatasetError as exc:
        return dataset_error(exc)
    except (SourceUnavailable, EphemerisError) as exc:
        return JSONResponse(
            status_code=503,
            content=dict(
                contract_version="1.0",
                error_code="SOURCE_UNAVAILABLE",
                detail=str(exc),
                fallback="NONE",
            ),
        )


@router.post("/datasets/{dataset_id}/analysis", response_model=CombinedResult)
def analyze(
    dataset_id: str,
    request: CellAnalysisRequest,
    service: UnifiedDataService = Depends(get_service),
):
    try:
        return service.analyze(dataset_id, request.cell_id, request)
    except DatasetError as exc:
        return dataset_error(exc)
    except (SourceUnavailable, EphemerisError) as exc:
        return JSONResponse(
            status_code=503,
            content=dict(
                contract_version="1.0",
                error_code="SOURCE_UNAVAILABLE",
                detail=str(exc),
                fallback="NONE",
            ),
        )
    except OSError:
        return JSONResponse(
            status_code=503,
            content=dict(
                contract_version="1.0",
                error_code="STORAGE_UNAVAILABLE",
                detail="Local scientific data storage unavailable",
                fallback="NONE",
            ),
        )


async def handle_dataset_error(request, exc):
    return dataset_error(exc)


def install(app):
    app.include_router(router)
    app.add_exception_handler(DatasetError, handle_dataset_error)
