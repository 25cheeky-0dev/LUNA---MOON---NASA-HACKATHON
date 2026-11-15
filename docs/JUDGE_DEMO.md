# WISPR judge demonstration

Use the local production preview described in the root README. The website may run a different release; do not substitute its UI for these screenshots.

## Three-minute presentation

1. **Explorer — 20 seconds:** “These are two original geographic cells from the NASA LOLA Site04 grid. We retain their identities, coordinates and provenance.” Select each footprint and expand the source disclosure if asked. [Screenshot](evidence/judge/WISPR-judge-01.jpg)
2. **Terrain — 25 seconds:** “Elevation describes height, slope describes inclination, and plane-fit roughness describes irregularity at this sampling scale. Unknown accuracy remains unknown; these are not safe-landing certifications.” Save both candidates. [Screenshot](evidence/judge/WISPR-judge-02.jpg)
3. **Candidates — 25 seconds:** “The original location is the first selected cell. We use a seven-day study, hourly samples and a one-hour shared-window requirement.” Keep the recorded dates, acknowledge missing terrain uncertainty, then evaluate. [Screenshot](evidence/judge/WISPR-judge-03.jpg)
4. **Timing — 45 seconds:** “The same ground changes from about 99.82 hours to the full 168-hour shared window after a seven-day shift. Both studies have equal durations. That 168-hour value is capped by the study, and the model is an ideal horizon. Sunlight is not electrical power and Earth visibility is not a communications guarantee.” The original cell difference is approximately 21 seconds, below the hourly cadence. [Screenshot](evidence/judge/WISPR-judge-04.jpg)
5. **Rescue — 25 seconds:** “The original cell still qualifies, so the engine keeps it. We rank only evaluated candidates satisfying the supplied constraints.” Optionally set maximum slope to zero: both real cells are excluded, with no invented replacement. Clear that constraint and reevaluate to restore the documented example. [Screenshot](evidence/judge/WISPR-judge-05.jpg)
6. **Report — 20 seconds:** “The readable report includes a summary picture and the complete analyzed evidence. Every number can be traced to its input, source hash and model.” Download the ZIP. [Screenshot](evidence/judge/WISPR-judge-06.jpg)

## Recovery and unsupported cases

- A date outside the recorded query coverage returns unknown. Explain the missing source; do not switch to synthetic fixtures.
- A report that expired after restart or cache eviction returns an actionable error; reevaluate before downloading again.
- A missing configured dataset returns an explicit error. Recorded mode needs only the committed two-cell fixture and NASA cache.
- Editing inputs invalidates the displayed result and report. A late response from an earlier request is ignored.
- Refresh preserves selected candidates and settings if the dataset hash still matches. It does not restore an unverified old analysis result.
- AI is optional. This branch has no configured local provider and uses the manual form; no embeddings or Gemini claim is necessary for the demonstration.

## Reproduce without the browser

From `backend`, run `uv run --no-sync python -m scripts.reproduce_judge --output ../docs/evidence/judge/reproduction`.
This executes the same engine with authentic recorded NASA responses, then writes Markdown, SVG, JSON and a request file. The raw NASA cache hashes and headers are checked before reuse. The evidence JSON records output timestamps, so a new run can have different generated metadata while preserving the physical results and source hashes.
