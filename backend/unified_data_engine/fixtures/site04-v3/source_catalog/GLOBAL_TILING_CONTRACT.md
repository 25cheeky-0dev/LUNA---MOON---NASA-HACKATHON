# Proposed global Moon tiling contract — **not implemented**

## Boundary between test and future global project

- **Implemented:** one original, verified NASA Site04 south-polar raster; 4 independent 1 km × 1 km processing tiles with one real native-source-pixel halo, covering the original 400 Site04 cells. Original `SITE04_R###_C###` keys stay frozen. The tile processor's V3 version does **not** rename the V2 grid rows.
- **Not implemented:** entire Moon partition, source coverage validation outside Site04, downloading regional data, Moon global multi-projection ingestion, resampling across product seams, and global tile-to-tile geometric neighbor topology.

## Region and projection families

| Zone | Preferred source / metric geometry | Important caveat |
|---|---|---|
| Local Shackleton Rim | Verified Site04 5 m NASA Moon south-polar stereographic | Interpolated DEM; not global or direct 5 m laser samples |
| South high latitudes | NASA LOLA South 20 m and other polar rasters | Choose south stereographic **only for this zone**; quality raster required to assess holes |
| North high latitudes | NASA LOLA North 20 m and other polar rasters | Use **north** polar stereographic; not the Site04 CRS |
| Mid-latitudes 60S–60N | SLDEM2015 tiled 512 ppd + quality mask | 512 pixels / *degree*; metric pixel size is not constant |
| Source seams and fallback | LOLA GDR 128 ppd or verified region-specific source | Coarser spatial resolution; don't claim uniform 100 m effective accuracy |

Store PDS labels and full original GeoTIFF/IMG/JP2 source files, including masks, unmodified. Be cautious: PDS products can store scaled elevation DNs rather than metre values. A source candidate is not a downloaded or validated source. Quality is a documented limitation when associated rasters are unavailable.

## Globally unique cell IDs (future only)

Proposed immutable format: `MOON_G{grid_config_id}_T{tile_id}_R{row:05d}_C{column:05d}`.

Example (illustrative, not an existing cell): `MOON_G0001_TSP_X0003_Y0008_R00012_C00009`.

- `grid_config_id` is frozen to the geometry, base sampling, tiling scheme and projection profile. **Scientific updates that don't move cells** should increment `calculation_version` rather than change the key.
- `tile_id` is unique within that grid configuration; assign from a deterministic global tile catalog containing explicit geographic footprints and the selected local-projection CRS. E.g., each tile family can use signed equal-distance projected tile offsets in its own declared regional frame. IDs must not be generated from *floating-point* coordinates rounded at runtime.
- `row` and `column` are integer indices in that tile's native grid; `cell_id` is the frozen primary key.
- Adjacent tile polygons must be compared in one common **Moon** coordinate system; latitude/longitude alone are not planar metre footprints. A given spatial point cannot be assigned to two active cells in the same grid layer. At overlapping DEM sources, choose a primary source explicitly and record alternatives.
- Existing `SITE04_R###_C###` IDs are a special legacy namespace and remain unchanged, even where their source/quality metadata is revised.

## Per-tile data contract

- `tile_id`, `grid_config_id`, `calculation_version`, source archive and checksum; `body=Moon`, source frame, horizontal CRS WKT/PROJ parameters, transformation method, longitude convention; full affine transform and 2D polygon footprint.
- Native `source_window` and `halo_window` in source pixel indices. Halo width is **exactly one native pixel** for centered-difference derivative; no zero padding at boundaries.
- Source pixel size and its angular/metric units, nodata representation, source raster version and product-specific height scaling / vertical reference.
- Per cell: frozen `cell_id`, row, column, projected center and polygon, planetocentric lat/east-positive lon (with explicit frame), source pixel count, valid fraction, pixel support, slope/roughness definitions, and `null` for unknown quality/uncertainty. Maintain a per-pixel **derived** validity mask independently of the untouched source mask.
- `source_change` and `resolution_change` indicators along seams. A tile must not silently use a fallback value from a neighboring dataset if its primary source has a gap.
- Uncertainty when provided may be heterogeneous. Record which uncertainty field the number describes and how it was aggregated; do not synthesize precision from native pixel spacing.

## Data layers kept separate

1. **Source layer**: original NASA PDS labels/raster bytes/quality rasters, checksums, untouched (authoritative).
2. **Derived grid layer**: cell summaries, polygons and neighbor topology, provenance/quality.
3. **Optional normalized-vector layer**: independently versioned raw feature keys, normalization algorithm and fitting sample, output normalized numbers. **This current engine does not produce vectors or semantic embeddings.**

A grid mean, max slope and roughness cannot reconstruct all raw heights. Retaining untouched original source data is the only defensible local interpretation of "no loss." This is not proof that the DEM itself preserves raw LOLA shots.

## Required ingestion gates before global tiles

1. Download exact selected source tile and detached PDS labels/ancillary quality bands.
2. Read raster shape, origin, projection/frame, scale/offset, units, reference sphere and NoData from source metadata; reject ambiguities.
3. Test 3 control locations (including a tile boundary), latitude/longitude round-trip and projected polygon areas. Include seams at 180-degree longitude and pole neighborhoods.
4. Choose and freeze per-region local mapping/projection; do **not** project all lunar cells with the Site04 south stereographic CRS.
5. Convert scaled heights only with verified source formulas. Check datum compatibility before joining to celestial observer-height calculations.
6. Compute in one-tile memory with source-native pixel halo, record exact source windows and pixel support, preserve missing cells as null and flagged.
7. Test seam geometry and source differences; where source resolution changes, keep an explicit boundary and comparability warning.
8. Run standard PyArrow or DuckDB read tests before merging multi-tile Parquet into shared production datasets.

## Official sources consulted

- NASA PGDA Site04: https://pgda.gsfc.nasa.gov/products/78
- NASA PGDA South Pole large-area: https://pgda.gsfc.nasa.gov/products/90
- NASA PGDA North Pole large-area: https://pgda.gsfc.nasa.gov/products/98
- NASA PGDA SLDEM2015: https://pgda.gsfc.nasa.gov/products/54
- NASA/PDS LOLA GDRDEM: https://ode.rsl.wustl.edu/mercury/pagehelp/Content/Missions_Instruments/Lunar%20Reconnaissance%20Orbiter%20%28LRO%29/LOLA/GDR/GDRDEM.htm
- PDS instrument and archive: https://pds-geosciences.wustl.edu/missions/lro/lola.htm
