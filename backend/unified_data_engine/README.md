# WISPR Unified Data Engine — frozen Site04 V3 integration

This component joins the **existing real V3 terrain package** to WISPR's NASA JPL Horizons
Celestial Engine. It adds data APIs, separate physical/normalized numerical vectors,
selected-cell analyses and bounded original/seven-day-delay comparisons. It does not
generate grids, build V4, claim full-Moon coverage, issue mission commands or certify landing sites.

## Architecture and versions

`adapters.py` recognizes the immutable V3 package layout; `loader.py` independently reads
Parquet with PyArrow and validates geometry with Shapely and lunar coordinates with PyProj.
`registry.py` exposes only operator-registered directories. `vectors.py` fits and exports
static numerical features. `coordinates.py` is the explicit boundary to Horizons.
`service.py` composes terrain, vectors, the existing Celestial Engine and visibility models.
`terrain_bridge.py` supplies the selected observer to the existing local-horizon provider.
`comparisons.py` bounds comparisons; `api.py` adds routes without replacing any existing API.

The integration contract is **1.0**. V3's original baseline `grid_version=2.0.0` remains
unchanged, while `tile_processing_version=3.0.0` identifies the supplied provenance layer.
All `SITE04_R..._C...` IDs and source values are preserved. Version labels are not appended
to IDs. Numerical fits have their own `terrain-population-zscore-v1` version and checksum.

The versioned loader also has a `manifest-v1` interface for explicitly declared partitions,
CRSs, asset mappings and checksums. This is tested using a **synthetic test-only** north-polar,
two-partition, 12-cell, 250 m configuration. It proves the loader has no hard-coded 400-cell
count, Site04 boundary or resolution. It does not implement or validate any actual V4
package. Unknown interface/adapter versions fail explicitly; no automatic format guessing.

## Source and scientific interpretation

Original V3 assets are preserved byte-for-byte under `fixtures/site04-v3/`: three Parquet
tables, baseline metadata, tile metadata and all 400 JSONL provenance records, package
checksum manifest, source catalog and validation reports. The 40 MB original DEM, GLB and
previews remain in the supplied external package; they are not duplicated in Git. No grid
generator from the package is executed or modified. Copied producer documents are source
provenance, not instructions for this application.

Official references reviewed November 14, 2026:

- [NASA PGDA product 78](https://pgda.gsfc.nasa.gov/products/78): Site04 Shackleton rim,
  interpolated LOLA elevation, projected metres and MOON_ME/DE421 frame.
- [NASA Horizons manual](https://ssd.jpl.nasa.gov/horizons/manual.html): lunar mean-Earth
  frame, observer coordinates, positive-east longitude and quantity 4 apparent angles.
- [Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) and
  [NASA fair-use policy](https://ssd-api.jpl.nasa.gov/doc/).

All three real Parquet files were independently opened by PyArrow: 400 grid cells, 400 WKB
polygons and 1520 directed neighbor rows. Validation checks source checksums, required
metadata, global ID uniqueness, exact grid/geometry ID sets, declared counts, duplicated
attributes, lunar spherical metre CRS, projection/inverse-projection consistency, polygon
validity and center containment, bounding boxes, reciprocal neighbor references, shared
edge lengths, raw measurement ranges, frozen row/column IDs and V3 provenance equality.
Source terrain statistics are checked for consistency, not recomputed from every DEM pixel.
Checksums verify identity against the supplied manifest, not a NASA digital signature.

V3 geographic latitude is **planetocentric**; longitude is east-positive **[-180,180)**.
The validated WKT uses a 1737400 m lunar sphere. On that sphere, planetocentric and
planetodetic latitude coincide; the adapter applies identity latitude and `longitude % 360`
only when constructing a Horizons request. Original coordinates remain in the response.
The inverse-projection numerical tolerance is 1e-8 degrees / 1 mm round trip; these are
consistency tolerances, not claimed DEM geolocation accuracy. Source frames other than
the explicitly supported lunar ME/DE421 sphere are rejected rather than approximated.

**DEM elevation is never used as Horizons altitude.** `horizons_altitude_km` is an explicit
independent input, default 0 above the Horizons reference sphere. The terrain observer's
height above DEM ground is another independent input, default 1 m. A cell's mean terrain
elevation can differ from the source pixel sampled exactly at its center; both are retained.
No conversion between these vertical references is claimed.

The existing horizon provider can sample the original, hash-checked DEM at the **selected
cell center**, using its lunar CRS, source ground height, geodesic rays and curvature model.
The optional selected-observer/raster-loader hook preserves all existing provider calls.
Only finite local coverage is available. The returned profile is PARTIAL, with
`far_field_complete=false`; missing rasters/dependencies/NoData yield UNAVAILABLE.
Terrain visibility remains **UNKNOWN**, including when the profile suggests clearance,
because complete horizon coverage and matching observer-height references are unresolved.
No local ridge is used to infer a confirmed mission outcome across these mismatched references.

Geometric visibility uses the existing piecewise-linear, adjacent-sample target-center
model above an ideal zero-degree plane. Results are MODEL_ESTIMATE, not proof of continuous
physical sunlight or communications. Missing samples remain UNKNOWN and break continuity.
Solar disk, illumination/power models, antennas, radio budgets and mission eligibility
remain downstream work. LOLA shot counts and uncertainty layers absent from V3 stay null;
an interpolated 5 m DEM pixel is not treated as an independent laser observation.

## Install and register a dataset

From `backend/`, use Python 3.12+:

```powershell
uv sync --locked --extra unified --extra celestial --extra terrain --extra test --extra lint
$env:WISPR_DATASETS_CONFIG = (Resolve-Path unified_data_engine/datasets.example.json).Path
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Without uv, install `python -m pip install -e '.[unified,celestial,terrain,test,lint]'`.
The unified extra adds PyArrow, PyProj and Shapely; NumPy is a transitive geometry dependency.
The existing terrain extra supplies Rasterio for optional real DEM horizon sampling.
No database, embeddings, LLM, frontend or cloud infrastructure is required.

The example registry uses the bundled real V3 tables/provenance, with the original source
DEM explicitly unavailable. To enable real source-raster profiles, create an operator-owned
registry outside source fixtures:

```json
{
  "schema_version": "1.0",
  "datasets": [{
    "dataset_id": "site04-v3",
    "root": "C:/path/to/WISPR_Site04_Tiling_V3",
    "adapter": "site04-v3"
  }]
}
```

Set `WISPR_DATASETS_CONFIG` to that file. Relative roots resolve against the registry file.
HTTP clients supply dataset/cell IDs, never filesystem paths or source URLs. No registry
configuration means an empty discovery list; no synthetic/demo dataset is silently selected.
Known registered but unavailable datasets return structured errors; discovery reports
individual dataset failures without concealing other entries.

Dataset ingestion is lazy and cached as a validated snapshot. Restart/recreate the registry
to ingest revised files. Changed table/metadata fingerprints invalidate cell access rather
than silently mixing versions. Default ingestion budgets: one million cells, 10000 partitions,
four cached partitions, 128 registered datasets. Limits are operator-configurable. No global
source coverage or untested production-scale performance is claimed.

NASA cache configuration, retry policy, source versions, TLS and single-process request
coordination are inherited from `celestial_engine/README.md`. Use one NASA-calling backend
worker until a shared cross-process request queue/gate exists. Deployments also require
authentication, quotas, monitoring and cache retention.

## API contract 1.0

Interactive OpenAPI: `/docs`. Existing endpoints remain unchanged.

| Method/path | Result |
|---|---|
| GET `/api/v1/data/datasets` | Registered dataset availability, versions and validation metadata |
| GET `/api/v1/data/datasets/{dataset_id}` | Dataset snapshot, counts, source/checksum integrity |
| GET `/api/v1/data/datasets/{dataset_id}/cells` | Paginated/filterable IDs |
| GET `/api/v1/data/datasets/{dataset_id}/cells/{cell_id}` | Original terrain, coordinates, WKB as lossless hex, neighbors, quality/provenance |
| GET `/api/v1/data/datasets/{dataset_id}/vectors` | Paginated numerical vectors and fit metadata |
| GET `/api/v1/data/datasets/{dataset_id}/vectors/{cell_id}` | Raw and normalized features, validity and calculation version |
| GET `/api/v1/data/datasets/{dataset_id}/similarity?cell_id=...&limit=10` | Bounded nearest numerical terrain comparisons |
| POST `/api/v1/data/datasets/{dataset_id}/analysis` | Selected-cell terrain/vector/NASA/visibility response |
| POST `/api/v1/data/datasets/{dataset_id}/comparisons` | Two–four cells, original and exactly seven-day-delayed intervals |

Cell filters: `elevation_min_m`, `elevation_max_m`, `slope_max_deg`, `roughness_max_m`,
`valid_only` (default true), `offset`, `limit` (1–1000). Static endpoints never query NASA.
Similarity uses Euclidean distance between the same dataset's z-score vectors and requires
compatible calculation versions. Top-k storage is bounded, limit 1–100. It measures only
terrain-feature proximity, not celestial similarity, confidence or landing suitability.

Example analysis request, using the exact selected cell center server-side:

```json
{
  "cell_id": "SITE04_R000_C000",
  "start_utc": "2026-11-15T00:00:00Z",
  "end_utc": "2026-11-16T00:00:00Z",
  "step_minutes": 60,
  "horizons_altitude_km": 0.0,
  "observer_height_above_dem_m": 1.0,
  "terrain_azimuth_step_deg": 10,
  "min_shared_window_minutes": 180,
  "verified_cache_only": false
}
```

Response groups: `contract_version`, `cell` (original terrain/geometry/neighbors/source
coordinates/quality/provenance), `terrain_vector`, `observer` (adapted coordinates and
explicit vertical-reference status), `ephemeris` (unchanged NASA records/metadata/quality),
`visibility` (modeled geometric samples/windows plus separate terrain profile/UNKNOWN),
`quality`, `provenance`, `limitations`. Complete executed examples are in `outputs/`.
Raw source measurements are not rounded, normalized in place or replaced by imputed values.
Nonfinite raw values become JSON null with an explicit missing-field list and original
Parquet asset checksum; invalid vectors have null normalized values.

Comparison body uses the same settings with `cell_ids` in place of `cell_id`:

```json
{
  "cell_ids": ["SITE04_R000_C000", "SITE04_R000_C001"],
  "start_utc": "2026-11-15T00:00:00Z",
  "end_utc": "2026-11-16T00:00:00Z",
  "step_minutes": 60,
  "delay_hours": 168
}
```

All comparisons use identical intervals within each scenario, cadence, observer settings,
calculation versions and geometric model. Limits: 2–4 unique valid cells, at most 48 hours
per interval and 2000 total scenario timestamps. Every cell/date/budget is validated before
NASA access. Results have `original` and `delayed_168h` scenario groups and normalized terrain
distances. They do not select an optimal site or recommend a landing date. A failed upstream
query fails explicitly; no substitute science or incomplete-success scenario is fabricated.

Errors: 404 DATASET_NOT_FOUND/CELL_NOT_FOUND; 422 invalid input, unsupported schema/frame,
checksum/geometry/topology inconsistency or exceeded budgets; 409 DATASET_CHANGED; 503
unavailable dataset/storage/dependency/NASA. Error responses include `error_code`, `detail`,
`contract_version=1.0` and `fallback=NONE`. Dataset discovery is HTTP 200 with explicit
per-dataset UNAVAILABLE status when a registered entry cannot be loaded.

## Numerical vector storage and reproducibility

Feature order is `[elevation_m, slope_deg, roughness_m]`, units `[m, degree, m]`.
Population z-score uses all valid, finite V3 cells. The fit stores means, population
standard deviations, source dataset/snapshot/version, method and SHA-256. Constant
observed features normalize to zero; missing measurements remain null and are excluded
from fitting. No LLM or trained semantic model is involved.

`export_vectors` writes **separate** `terrain_vectors_raw.parquet` and
`terrain_vectors_normalized.parquet`, plus `normalization_metadata.json`. IDs, validity,
source-quality labels and calculation versions accompany both tables. Uncompressed
float64 Parquet preserves canonical physical values; normalization does not overwrite
baseline terrain. The CLI writes the combined JSON and both vector tables:

```powershell
.\.venv\Scripts\python -m unified_data_engine --root C:/path/to/WISPR_Site04_Tiling_V3 --adapter site04-v3 --dataset-id site04-v3 --cell-id SITE04_R000_C000 --start-utc 2026-11-15T00:00:00Z --end-utc 2026-11-16T00:00:00Z --output data/v3_analysis.json
```

For exact recorded replay, copy `fixtures/horizons/*.json` to your `CELESTIAL_CACHE_DIR`
and send `verified_cache_only=true`. These are authentic recorded responses for the two
demonstrated cell centers and two demonstrated intervals, not a cache for arbitrary cells.

## Verification

```powershell
.\.venv\Scripts\python -m pytest -q -m 'not live'
.\.venv\Scripts\ruff check celestial_engine unified_data_engine
.\.venv\Scripts\ruff format --check celestial_engine unified_data_engine
$env:WISPR_V3_LIVE_TEST='1'
$env:WISPR_V3_PACKAGE='C:/path/to/WISPR_Site04_Tiling_V3'
.\.venv\Scripts\python -m pytest unified_data_engine/tests/test_live_v3.py -q
```

Windows short-path systems can add `--basetemp C:/tmp/wispr-tests` in a writable parent.
Offline tests use all real V3 rows and authentic recorded NASA responses. Deliberately
corrupted inputs, missing-observation copies and the alternate grid are labeled test-only.
The live test requires NASA access and the original supplied DEM, checks the real single-cell
API response and two-cell original/delayed comparison, and saves artifacts when
`WISPR_V3_DEMO_OUTPUT` is configured. A separate actual uvicorn HTTP test was also executed.
See `VERIFICATION.md` for measured outputs and test evidence.
