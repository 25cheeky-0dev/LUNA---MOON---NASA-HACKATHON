# WISPR final hackathon audit

Audit date: 2026-11-15. Base: `ba5c1f59710bbef2653069581dd9f9dcc56994dd` (`main`) in `25cheeky-0dev/LUNA---MOON---NASA-HACKATHON`. Implementation branch: `feature/judge-ready-final`.

## Repository and deployment

The pre-existing local checkout was clean on `feature/adaptive-regions-agent`, commit `1e07af5c3a2f9e18daade846e7e0b41e5a40b106`, with an origin pointing to the different `NASA-LUnar` repository. That branch was preserved. The requested repository was fetched and the new branch created from its actual current main; the old release was not substituted for it.

Cloud Run inspection confirmed `nasa-lunar-00025-dup` serves 100% of normal traffic. The live browser showed the surface/Moon explorer, recorded Site04 mission, KEEP decision, 168-hour delayed results, and reproducible-report link. It did not show this branch's six-stage Judge Mode. The live planner label said “Gemini not connected”; this does not establish the status of every separate report integration in that deployed release.

The requested repository lacks the other branch's React 3D viewers, adaptive-region modules, Gemini adapter, global 118 m extraction and crater-report modules. These were not deleted by this PR: they were absent at the requested base. Exact deployed Git SHA is not attested by the inspected service metadata. Do not claim this branch is a superset of the running service, merge it over the other branch, or redeploy it blindly. No cloud service or traffic change was made in this audit. [Observed deployment metadata](evidence/judge/deployment.json) · [Live screenshot](evidence/judge/WISPR-existing-deployment.jpg).

## Feature audit

| Feature | Actual status | Evidence | Problem | Fix / disposition | Priority |
|---|---|---|---|---|---|
| Backend installation | Repaired; locked install passes | `pyproject.toml`, `uv.lock`; `uv sync --locked` | Committed unresolved merge markers blocked TOML parsing; lock also conflicted | Preserve both global and terrain-validation extras and all 49 locked packages | P0 resolved |
| CI workflow | Repaired; equivalent local checks pass | `.github/workflows/celestial-engine.yml` | Merge markers invalidated workflow; frontend absent from checks | Preserve stricter backend checks, add frontend clean install/test/build and branch trigger | P0 resolved |
| Original/+7-day comparison | Recomputed from authentic recordings | `tests/test_judge.py`, reproduction/evidence.json | Legacy UI did not offer the native-cell side-by-side story | Add paired timelines with equal durations, explicit cadence/model and full-window cap | P0 resolved |
| Candidate identity | Verified for the two curated cells | API regression + browser refresh | No curated native-cell persistence flow in requested frontend | Persist IDs, coordinates, metadata/hash and settings; invalidate old analysis on edits | P1 resolved |
| Terrain statistics | Source-backed extracted values | Original fixture and untouched static vectors | Resolution/accuracy could be conflated | Show native spacing, aggregation and unknown accuracy; no safe-landing labels | P0 resolved |
| Terrain horizons | Conditional local diagnostics; not terrain-certified visibility | `TERRAIN_HORIZON_VALIDATION.md`, horizon tests | Unresolved reference alignment and incomplete distant skyline | Preserve unknown states; expose partial model honestly; full external package checks still unavailable | P0 limitation |
| Global explorer | Existing configured atlas preserved | `GlobalExplorer.tsx`, real global-data tests | Full-Moon index could be confused with high-resolution terrain | Keep technical interface and documented source coverage; do not claim global high-resolution extraction in this branch | P1 limitation |
| Rescue/ranking | Existing deterministic selected-scope engine passes | Tests for unsupported ephemerides, slope exclusion and partial terrain | Missing data must not become a winning alternative | Rank complete qualifying evidence only; expose exclusions and insufficient-data outcome | P0 verified |
| Vector/retrieval system | Physical normalized vectors and keyword retrieval | `VECTOR_RETRIEVAL_CONTRACT.md`, global tests | Embedding-search wording would overclaim | Explicitly state no configured embedding model; never mix keyword and physical scores | P1 documented |
| AI | Existing Groq/NVIDIA structured extraction; no local key/model configured | `providers/interpret.py`, `test_interpret.py`, backend status | Cannot verify a live provider without configured access | Keep manual form; JSON/Pydantic validation and sanitized failure behavior retained; no new physical AI predictions | P1 limitation |
| Report export | Exact analyzed evidence preserved | ZIP regression, browser download, reproducible example | Raw JSON alone is hard to present; recalculation could change export | Markdown + summary SVG + JSON, hashed evidence, bounded result store and explicit expiry errors | P0 resolved |
| Frontend test runner | Clean run | `frontend-test.txt` | Dependency-scan shutdown produced spurious errors after fixture success | Disable unneeded dependency discovery in the fixture harness | P1 resolved |
| Production UI | Six stages browser-verified; no captured console errors | Six screenshots, browser observations | Technical evidence crowded the presentation | Collapsible provenance; no synthetic figures, development examples or empty charts in Judge Mode | P1 resolved |
| Mobile layout | Responsive CSS implemented; browser viewport verification incomplete | CSS breakpoint; viewport attempt remained 1265 px | Browser override did not apply to the target tab | Do not claim a verified 390 px device test; verify on a real narrow viewport before public release | P2 limitation |

## Scientific findings

- Both comparisons were recomputed through `AnalysisEngine.delay`, `CelestialService` and `HorizonsClient`, using exact-match **VERIFIED_CACHE** deliveries. Raw recordings are committed under `backend/tests/fixtures/unified_nasa`; they are authentic recorded NASA responses, not synthetic fixtures. A separately enabled live Horizons test passed.
- Original interval: **2026-11-15 00:00 to November 22 00:00 UTC**. Delayed interval: **November 22 to November 29 00:00 UTC**. Each duration is **168 hours**, each date shift exactly **604800 seconds**, and each cell has **169 inclusive observations** at **60-minute cadence**.
- Original longest shared windows: C000 **5988.9515639 minutes**; C001 **5988.594435616667 minutes**. Both delayed windows are **10080 minutes**, exactly the evaluation duration. The result is censored at the interval endpoints and does not prove uninterrupted visibility beyond them.
- Model: **GEOMETRIC_IDEAL**. Target-center elevations strictly above the ideal local normal plane; adjacent known samples support piecewise-linear crossing estimates. No terrain occlusion, finite Sun disk, power model or radio link budget is included. Hourly cadence bounds interpretation; decimal output precision is not an independently measured timing accuracy or confidence interval.
- The original difference is approximately **21.43 seconds**, far below one cadence. There is no scientifically justified claim that one cell is superior on these figures alone. Deterministic ordering is not statistical significance.
- C000 latitude/longitude are **−89.7787655990766°, −167.51751061504552°**; C001 **−89.779454879477°, −168.3540257515168°**. Longitudes are wrapped to east-positive [0,360) for Horizons. Each returned observation is checked against the selected cell and expected UTC timestamp.
- The declared frame is **MOON_ME / DE421**. The engine verifies the spherical 1737.4 km lunar center shape in both NASA headers before accepting the source grid's spherical-latitude identity. Observer altitude is **0 km above the Horizons lunar reference**, not the DEM elevation. The separate **1 m terrain observer-height setting** does not modify that astronomical altitude.
- Original DEM SHA-256: `38ff70dbdf2f066c2cfa94a646c3a59d653ce7f6b4528b15fc1b43ee397ce758`. This audit preserves the recorded provenance and verifies the extracted fixture/caches; it does not claim a fresh independent full-raster check without the external package. The unresolved DEM/Horizons vertical-reference alignment remains explicit.
- Grid version **2.0.0**, processing version **3.0.0**, original cell IDs, static measurements and source metadata are unchanged. JSON reports retain source URLs, raw hashes, query parameters, observer settings, exclusions, models and limitations.

## Executed checks

| Check | Result |
|---|---|
| Baseline frontend fixture tests/build | Passed; fixture harness emitted a dependency-scan shutdown error, subsequently repaired |
| Baseline backend | Could not start: invalid TOML merge markers |
| Locked environment installation after repair | Passed, 49 packages resolved; package versions preserved |
| Full suite with available real global products and live NASA enabled | **220 passed, 4 skipped**, one upstream Starlette/httpx deprecation warning |
| Offline suite before optional source checks | **215 passed, 9 skipped** |
| New authentic Judge Mode regressions | Six tests passed, included in totals |
| Existing AI output-schema validation/failure tests | Passed in full suite; no live provider claim |
| Generated scientific OpenAPI/TypeScript contract check | Passed after additive Judge schemas were exported |
| CI-equivalent Ruff checks and format checks | Passed |
| Clean frontend lockfile install | Passed in isolated task folder, 0 npm-reported vulnerabilities |
| Frontend fixture suite | Passed; six explicitly synthetic interface outcomes |
| Production TypeScript/Vite build | Passed, 34 transformed modules |
| Browser stages | Explorer, terrain, saved candidates, paired comparison, rescue and report download observed |
| Browser persistence | Both cell selections and acknowledged settings survived refresh; results require reevaluation |
| Browser errors | No captured error/warning entries in the tested Judge flow |
| Git whitespace/conflict checks | Passed; no tracked merge markers remain |

Four remaining skips need the external full frozen V3 package: two integration checks and two full-raster terrain-horizon checks. The documented Downloads path does not exist locally. Existing real extracted-cell fixtures still run; they are not represented as validation of the entire absent package.

The first in-place `npm ci` encountered Windows EPERM on an esbuild binary held by an existing process. No unrelated process was killed. A separate clean frontend directory using the same source and lockfile installed, tested and built successfully; its production artifact was used for final preview. See the retained installation logs.

## Evidence and reproduction

- [Final backend test output](evidence/judge/final-tests.txt)
- [Frontend clean installation](evidence/judge/frontend-clean-install.txt), [fixture tests](evidence/judge/frontend-test.txt), [build](evidence/judge/frontend-build.txt)
- [Readable reproduced report](evidence/judge/reproduction/report.md), [summary SVG](evidence/judge/reproduction/summary.svg), [exact evidence](evidence/judge/reproduction/evidence.json), [request](evidence/judge/reproduction/request.json)
- [Judge presentation script and six screenshots](JUDGE_DEMO.md)
- [Tracked source inventory](evidence/judge/inventory.txt)

From `backend`: `uv run --no-sync python -m scripts.reproduce_judge --output ../docs/evidence/judge/reproduction`.

## Release limits

This PR is for review; it does not merge main or redeploy Cloud Run. The repository/deployment divergence must be reconciled deliberately before a future deployment. Judge Mode currently curates two original Site04 cells; the existing general APIs remain intact. Reports are process-local, capped at 16 entries and may expire. Public hosting hardening and multi-instance persistence are not introduced by this local presentation adapter. AI provider execution, full external Site04 raster validation, narrow-device browser verification and exhaustive testing of every legacy technical-interface control remain unverified; none is presented as complete.
