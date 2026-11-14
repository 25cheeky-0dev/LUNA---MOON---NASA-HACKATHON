# Final V3 scientific integration — executed verification

Executed on November 14, 2026, against the original supplied
`WISPR_Site04_Tiled_Provenance_V3/WISPR_Site04_Tiling_V3` package.

## Results

- **181 offline tests passed**, including all existing backend/Celestial Engine tests and
  35 new real-V3, adapter, vector, API, quality and comparison tests. Two opt-in live tests
  were deselected during the offline run.
- **One real V3 live integration test passed**, exercising the full analysis and comparison
  API with the original GeoTIFF and eight sequential real NASA target queries.
- Real temporary uvicorn HTTP server also passed discovery, selected-cell analysis,
  paginated vectors, numerical similarity, 422 invalid-input and 404 unknown-dataset checks.
  Its 25 NASA records and terrain vector matched the live demonstration exactly. It was
  stopped after verification. HTTP replay used the verified cache, with no extra NASA calls.
- Ruff lint passed for both modules; format checks passed. Final diff whitespace check passed.
- Locked environment installed successfully. Local execution used Windows / CPython 3.15.2.
  CI runs Python 3.12/3.13 and is reported separately in the PR.
- Zero unresolved test failures. A nonblocking Starlette test-transport deprecation warning remains.

An initial synthetic test fixture inferred integer elevation storage and could not represent
the deliberately injected NaN. That test-only fixture was corrected to float64; the complete
suite then passed. No real terrain values were altered.

## Independent V3 validation

PyArrow opened 400 grid records, 400 geometry records and 1520 directed neighbor records.
The loader verified integrity against the supplied checksum manifest, original IDs,
table/header metadata, lunar projected CRS, source coordinates, WKB validity/containment/
bounds, reciprocal neighbor topology and shared edge lengths, source row/column indices,
declared origin/resolution, terrain value consistency and exact V3-to-baseline provenance joins.
Maximum geographic/projected numerical round-trip error: **2.426343734323133e-08 m**.
This is numerical consistency, not a claim of measurement accuracy.

Original package hashes verified:

| Asset | SHA-256 |
|---|---|
| baseline/grid.parquet | dc32b04162bd3db3e114ba816a1958f1ef918d7f38effa7eaee992ca32fa45e4 |
| baseline/grid_geometry.parquet | 2de40301a6f4cddbf572f57060c3b6637a03f681a6d084ed540ee29930dcf8b0 |
| baseline/neighbors.parquet | 952c3be5e22f1fefa9066f9354555d1935a73e58d0621bcde0e02d3ae27110e5 |
| baseline/grid_metadata.json | e2dd99b19aa03acd5c26f19791332b3191e274932ea454cf44accbdaeb1670b6 |
| Original NASA Site04 DEM | 38ff70dbdf2f066c2cfa94a646c3a59d653ce7f6b4528b15fc1b43ee397ce758 |

The source generator `engine/build_tiles.py`, DEM and original baseline files still match
the package's original hashes. No grid-generation, original terrain or original source data
was modified. Producer claims about independent Parquet interoperability are now supplemented
by this actual PyArrow read and independent consistency validation, not merely repeated.
Full DEM-derived elevation/slope/roughness recomputation is not claimed.

## Selected cell and vectors

`SITE04_R000_C000`, original baseline version 2.0.0 / tile processor version 3.0.0:

- Projected source center: X **-1450.0 m**, Y **-6550.0 m**.
- Original planetocentric latitude: **-89.7787655990766°**.
- Original east-positive signed longitude: **-167.51751061504552°**.
- Horizons boundary longitude: **192.48248938495448° east**.
- Raw vector `[elevation_m, slope_deg, roughness_m]`:
  **[1072.0976434326171, 32.13135594956228, 0.9163221785602584]**.
- Normalized vector, population z-score across 400 valid cells:
  **[1.6735529854764035, 0.07290276264206418, 0.32424098083283137]**.
- Normalization version: `terrain-population-zscore-v1`; fit checksum:
  `b9f6ccc2bb832152d5dcd416ac29c7fe5eb155610f60265fb697b676322a2d0c`.

Raw and normalized values are stored in separate 400-row Parquet files. Fit means, standard
deviations, versions and source snapshot hashes are in `normalization_metadata.json`.
The original raw terrain Parquet remains unchanged. Missing uncertainty/LOLA count fields
stay null and source quality remains `source_lola_count_and_uncertainty_not_supplied`.

## Actual NASA and modeled visibility

Selected interval: **2026-11-15T00:00:00Z through 2026-11-16T00:00:00Z**, hourly,
25 inclusive observations. Observer altitude: **0 km above Horizons' lunar reference**,
not the cell's 1072.0976 m mean elevation and not the DEM pixel's ground height.

First actual NASA record for `SITE04_R000_C000`:

| UTC | Sun azimuth ° | Sun elevation ° | Earth azimuth ° | Earth elevation ° |
|---|---:|---:|---:|---:|
| 2026-11-15 00:00 | 281.942847516 | 1.602146478 | 164.894021795 | -3.766403240 |

Both targets have valid ranges and exact requested timestamp alignment. All raw NASA
responses, exact query parameters, retrieval times, source headers, SHA-256 checksums,
API/parser versions and delivery labels are retained. Live response labels were LIVE;
offline/HTTP replay labels are VERIFIED_CACHE. The source observations are never relabeled
as synthetic or silently replaced.

The original DEM was sampled through the existing terrain-horizon provider at the exact
selected center. That pixel's sampled ground height is **1070.8323974609375 m**, which
differs from the cell mean. A 1 m above-DEM observer and 10° azimuth steps produced a
36-direction finite local profile. Coverage is **PARTIAL**, far-field completeness false,
and terrain visibility **UNKNOWN** throughout. The vertical-reference mismatch is explicit.

Compared with the separately evaluated `SITE04_R000_C001` using identical settings:

| Scenario | Cells | Modeled Sun fraction | Modeled Earth fraction | Modeled shared duration |
|---|---|---:|---:|---:|
| Nov 15–16 original | Both selected cells | 1.0 | 0.0 | 0 minutes |
| Nov 22–23 delayed 168 h | Both selected cells | 1.0 | 1.0 | 1440 minutes |

These are piecewise-linear **ideal-plane target-center MODEL_ESTIMATE** metrics, not
terrain-cleared illumination, radio availability or continuously verified mission windows.
Terrain visibility is UNKNOWN for every scenario. Normalized terrain distance between
the two cells: **0.8857876295009679**, using the same fit and calculation version.

## Reproducible artifacts

- `combined_analysis.json`: executed live full response.
- `comparison.json`: both real cells, original and exact seven-day-delayed scenarios.
- `http_analysis_response.json`: independently exercised actual HTTP response using verified cache.
- `analysis_request.json`, `comparison_request.json`: actual request bodies.
- `terrain_vectors_raw.parquet`, `terrain_vectors_normalized.parquet`, `normalization_metadata.json`.
- `dataset_validation.json`: counts, checksums, metadata and validation scope.
- `fixtures/horizons/`: eight authentic captured NASA cache entries for offline replay.

No V4 grid, full-Moon coverage, frontend, LLM, vector database or cloud deployment was built.
