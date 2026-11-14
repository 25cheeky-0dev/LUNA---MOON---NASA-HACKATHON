# WISPR Grid Engine — additive tiled/provenance update (V3)

**Status: Site04 tile-processor verified; global Moon tiling is planned only.**

This package preserves the previously built **400-cell / 2 km × 2 km V2 Site04 grid** exactly, together with its original NASA Site04 5 m DEM. It adds an independent tile-based measurement and provenance layer, without rekeying cells, modifying the source raster, or generating normalized vectors.

## Package contents

- `Site04_final_adj_5mpp_surf.tif` — unchanged original 3,200 × 3,200 NASA GeoTIFF (same SHA256 as V2).
- `baseline/` — unchanged V2 `grid.parquet`, `grid_geometry.parquet`, `neighbors.parquet`, `grid.geojson`, projection metadata, mesh, previews, and validation report.
- `engine/build_tiles.py` — source-window grid processor; four 1 km² Site04 tiles, **one real native 5 m source-pixel halo per tile**, independent from the baseline grid calculations.
- `tiles/SITE04_TILE_R##_C##/tile_metadata.json` — exact 200 × 200 source-pixel core offset and affine + 202 × 202 halo window, full source WKT, origin/footprint, source datum/quality flags.
- `tiles/SITE04_TILE_R##_C##/cells.jsonl` — 100 full per-cell derived records per tile (400 total), with original cell IDs, polygons, neighbors, raw terrain summaries and provenance. `null` signifies unavailable uncertainty/count, not zero.
- `tiles/.../derived_source_valid_mask.npy` — derived boolean pixel validity mask for each 200 × 200 core; raw source TIFF untouched.
- `tile_manifest.json` — tile index, transforms and coverage/gaps.
- `validation/tile_validation.json` — 400 legacy IDs and neighbor relationships verified, zero discrepancies with V2 source-derived measurements.
- `source_catalog/lunar_dem_source_candidates.json` — official NASA product families, intended coverage, pixel spacing, quality availability and download status. **Only Site04 was downloaded.**
- `source_catalog/GLOBAL_TILING_CONTRACT.md` — proposed global ID scheme and required multi-projection ingestion gates. Not an implementation of full-Moon coverage.

## Provenance and geometry contract

- Source body: Moon; NASA Site04 **MOON_ME / DE421**; original projected CRS from GeoTIFF WKT.
- Site04 cell center coordinates and polygon X/Y are native projected **metres**. Planetocentric `latitude` and east-positive `longitude` in **degrees [-180,180)** for longitude.
- Site04 cell keys remain **`SITE04_R000_C000`** etc.; never add grid/version identifiers to existing keys. Existing grid metadata still names `grid_version=2.0.0`; the new tile processor version is `3.0.0`.
- The GeoJSON in `baseline/` is **projected lunar**, not Earth RFC7946 GeoJSON. Consumers must use the lunar CRS in its sidecar.
- One source pixel is 5 m but **not equivalent to one independent LOLA shot**. The available original LDEM was interpolated. `source_pixel_count_valid` is a derived pixel count, not a spot count. `lola_shot_count` and `elevation_uncertainty_m` are intentionally null because LDEC and uncertainty rasters are not in this package.
- V2 elevation/slope/roughness definitions are preserved: native pixel average, centered finite-difference slope with 1-pixel halo, RMS of residuals after a cell plane fit. All raw data are unchanged. Existing grid cell values compare exactly with baseline under reproducible float64 computation.
- **No** full Moon projection, full Moon 3D surface, Sun/Earth engine, landing algorithm, vector normalization or embeddings here.

## Rebuild and QA

Dependencies: `python >=3.11`, `numpy`, `rasterio`.

```bash
python engine/build_tiles.py \
  --dem Site04_final_adj_5mpp_surf.tif \
  --baseline-geojson baseline/grid.geojson \
  --output .
```

Read `validation/tile_validation.json` and `tile_manifest.json`. For standard Parquet interoperability, verify baseline files on Manraj's environment with PyArrow / DuckDB. We did not run such a reader here.

## WISPR developer handoff

Use `baseline/grid.parquet` for the existing immutable 400-cell table; use `tiles/*/cells.jsonl` as **additional** per-cell provenance/quality, keyed on `cell_id`. Keep `tile_manifest.json` to load exact spatial footprints. The source DEM is included byte-for-byte for later local-horizon calculation. Do not interpret a Sun/Earth JPL Horizons observer-height join as approved until its altitude/reference convention is verified against the NASA DEM.
