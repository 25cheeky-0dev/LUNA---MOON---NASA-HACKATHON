# Terrain Horizon Engine V1

The library computes on-demand local skylines from the unchanged full Site04 DEM.
It extends `app.providers.terrain`, retains `GEOMETRIC_IDEAL` and `TERRAIN_PARTIAL`,
and does not change HTTP schemas, the Celestial Engine, Grid V3, or frontend files.
The additive comparison adapter returns `TERRAIN_BLOCKED`, `TERRAIN_VISIBLE`, or
`UNKNOWN`. Real Site04 results currently remain `UNKNOWN` for physical visibility.

## Install and run

From `backend`, install `pip install -e ".[terrain,test,terrain-validation]"`.
The original external V3 package is required; it is not copied into Git.

```python
from app.providers.terrain import compute_horizon
from app.providers.terrain_horizon import TerrainHorizonEngine
from app.providers.horizon_comparison import compare_ephemeris

engine = TerrainHorizonEngine.from_v3("/path/to/WISPR_Site04_Tiling_V3")
result = compute_horizon(
    "SITE04_R000_C000", 1.0, [23.123456, 90.0, 359.999], engine=engine
)
preview = engine.diagnostic_skyline("SITE04_R000_C000", 1.0, 1.0)

# ephemeris is an unchanged CelestialService EphemerisResult or its JSON dict.
# raw_sources contains the original NASA response bytes, not reconstructed CSV.
joined = compare_ephemeris(
    engine, "SITE04_R000_C000", 1.0, ephemeris,
    raw_sources={"sun": original_sun_bytes, "earth": original_earth_bytes},
)
```

Alternatively set `WISPR_TERRAIN_V3_DIR` and call the three-argument
`compute_horizon(cell_id, observer_height_m, azimuths_deg)` directly. Its two-entry
process cache reopens and revalidates when the DEM or package-manifest file size
or modification time changes. Explicit engines are immutable source snapshots;
construct a new engine after a package update. Never mutate engine settings or
cells in a running service. The per-engine LRU holds at most 128 results, with
locking around cache access and defensive result copies. Keys include original
ID and coordinates, actual raster SHA-256, observer height, normalized ordered
azimuths, reference settings, sample distance and algorithm version.

Only the requested cells receive ray calculations. Reading/validating all 400
original IDs during ingestion does not calculate their horizons. The native V3
reader verifies consumed files against the package manifest and retains original
cell coordinates; no grid or cell-mean elevation is substituted for the DEM.

## Provider integration

The existing `terrain.horizon(site_id, observer_height_m, az_step_deg,
position=(latitude, longitude))` contract is retained. It now delegates to the
same full-raster algorithm, using the existing configured DEM sidecar loader.
An optional `azimuths_deg` keyword overrides its diagnostic angular grid.
`terrain_metadata` and `heightmap` are unchanged.

For native V3 use `TerrainHorizonEngine.from_v3` directly: no invented sidecar is
needed. The Unified Science Engine should call `compare_ephemeris` **after** its
unchanged CelestialService call. This adapter computes every distinct requested
Sun/Earth azimuth, not an interpolation of the preview. Each result contains
`source_observation` (all original fields unchanged), `terrain.sun`, and
`terrain.earth`, plus original metadata and the exact-direction horizon output.

The existing HTTP analysis flow still uses its legacy preview and state names;
this change does not replace those public response states. Its internal reference
gate now additionally requires explicit vertical verification, so changing only
a manifest label cannot authorize terrain comparisons. Adopt the additive adapter
in a coordinated future API change if these new three-state decisions are to be
exposed through HTTP. No physical visibility claim should be taken from a preview.

## Geometry and sampling contract

The source CRS must be projected metres on the declared sphere. For Site04 its
radius is 1,737,400 m. Geographic ray azimuth is clockwise from north and uses
`pyproj.Geod(a=R, b=R)`, independent of polar-stereographic grid north. Longitudes
are east positive; input azimuths wrap modulo 360. Exact poles are rejected
because local azimuth requires an additional meridian convention. Numerical
geographic/projected center round trips must agree within 1 cm; this accounts for
PROJ precision extremely near the pole and is not a terrain-accuracy claim.

The full 3200 × 3200 source is loaded as a masked immutable snapshot. Sampling is
bilinear on source pixel centers. All four neighbors must be finite/unmasked;
there is no extrapolation or substitution across holes. The observer ground is
sampled identically at its actual center. Distances default to 2.5 m, at most half
a native pixel; smaller positive steps are configurable. The first invalid
interpolation ends the supported sample prefix. Outer half-pixel margins are
conservatively unsupported. A finite search budget can stop a ray but never
certifies completeness.

For the explicitly declared radial-height interpretation, let `z0` be the
sampled observer ground, `h` its radial height above terrain, `z` the sample,
and `offset` an independently justified constant radial datum conversion:

```text
ro = R + z0 + offset + h
rt = R + z  + offset
theta = geodesic_distance / R
up = (rt - ro) - 2 rt sin(theta/2)^2
horizontal = rt sin(theta)
elevation = atan2(up, horizontal)
```

This is Moon-centered vector geometry resolved against radial local up. The
half-angle form avoids subtractive cancellation. Both absolute radii are kept;
the former height-difference-only curvature helper is no longer used for rays.
That helper remains for backward compatibility.

## Reference and visibility gates

`ReferenceSettings` defaults to **unverified** radial-height interpretation.
Its numeric skylines are conditional diagnostics, not confirmed physical
directions. Evidence strings are caller-supplied scientific attestations, not
automatic proof. Do not set verification because the CRS has a sphere or rename
the package's vertical datum. If an independently documented height conversion
requires more than a constant radial offset, implement and validate that
conversion first; unsupported interpretations are rejected.

The adapter hashes the supplied original NASA bytes, reuses the existing NASA
parser to check each target, Moon center, MOON_ME frame, reference radii,
observer header and airless convention, and compares every retained timestamp
and angle to those parsed bytes. It also checks the request and each row's
observer against the selected center and DEM-derived absolute altitude. Missing
raw responses, wrong coordinates, wrong altitude, or an unverified datum leave
visibility unknown. Preserved observations may be a subset of the original
response; the validation report explicitly uses its first three UTC records.

A verified obstruction lower bound may establish `TERRAIN_BLOCKED` even though
the far field is unknown. Such a bound requires an independently supported hard
height-error bound, applied with terrain lower and observer upper radii. RMS
uncertainty is not a hard bound. Default Site04 has no such bound. Contact at
exact equality is conservatively unknown.

`TERRAIN_VISIBLE` additionally requires complete near and far terrain support,
verified resolution, and a conservative horizon **upper** bound. This finite
local engine never supplies these clearance certificates, so cannot emit visible
for real Site04. The classifier supports the state for future validated complete
models. Discrete sampled support is not continuous interval coverage: the
observer-to-first-sample interval, gaps between samples, and subpixel terrain
remain unresolved. `uncertainty_deg=null` means unknown, never zero.

Calculations are target-center only. They do not determine solar disk fractions,
full illumination, partial disk visibility, radio clearance, or a link budget.
No solar angular radius is silently assumed.

## Reproduce validation

```text
python -m scripts.validate_terrain_horizon --v3-root /path/to/WISPR_Site04_Tiling_V3 --output ../docs/evidence/terrain-horizon
```

Set `WISPR_REAL_V3_DIR` to the same directory, then run
`python -m pytest -q -m "not live"`. Without it the external-asset tests skip
explicitly. The script uses authentic recorded NASA responses already in the
repository, verifies their hashes/parsing, and makes no live-network claim.
It generates checksum/raster evidence, two full 1° skyline JSON files, a plot,
exact-direction NASA comparisons and a 2.5 m versus 1.25 m sampling check.
The finer-run difference is an observed sensitivity, **not** a worst-case bound.

See [the validation report](TERRAIN_HORIZON_VALIDATION.md) and
[machine-readable evidence](evidence/terrain-horizon/validation_summary.json).
