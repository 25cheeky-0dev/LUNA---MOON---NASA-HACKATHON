import { useEffect, useRef, useState } from "react";
import type {
  DelayResponse,
  DynamicVector,
  Metadata,
  app__integration__grid__Cell as Cell,
} from "../../docs/contracts/science.generated";
import { BASE } from "./lib/api";
import "./judge.css";

type Dataset = {
  metadata: Metadata;
  cells: Cell[];
  dataset_sha256: string;
  ai_status: string;
  note: string;
};
const stages = [
  "Lunar Explorer",
  "Analyze Terrain",
  "Compare Candidates",
  "Original vs +7 Days",
  "Mission Rescue",
  "Reproducible Report",
];
const STORAGE = "wispr-judge-candidates-v1";
const fmt = (v: number | null | undefined, suffix = "") =>
  v == null ? "Unknown" : `${v.toFixed(2)}${suffix}`;
async function call(path: string, body?: unknown) {
  const response = await fetch(`${BASE}/api/v1/judge/${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(120000),
  });
  if (!response.ok) {
    let detail = "";
    try {
      detail = JSON.stringify((await response.json()).detail);
    } catch {
      detail = response.statusText;
    }
    throw Error(`Request unavailable (${response.status}). ${detail}`);
  }
  return response;
}
function Windows({ d }: { d: DynamicVector }) {
  const start = Date.parse(d.start_utc),
    span = Date.parse(d.end_utc) - start;
  return (
    <div className="j-windows">
      {(["sun", "earth", "shared"] as const).map((body) => (
        <div key={body}>
          <span>
            {body === "sun" ? "Sun" : body === "earth" ? "Earth" : "Shared"}
          </span>
          <div className="j-track" aria-label={`${body} visibility intervals`}>
            {d.features.summary[`${body}_windows`].map((w, i) => (
              <i
                key={i}
                style={{
                  left: `${((Date.parse(w.start_utc) - start) / span) * 100}%`,
                  width: `${((Date.parse(w.end_utc) - Date.parse(w.start_utc)) / span) * 100}%`,
                }}
                title={`${w.start_utc} → ${w.end_utc}: ${w.duration_minutes.toFixed(2)} minutes`}
              />
            ))}
          </div>
        </div>
      ))}
      <small>
        Interval positions within this study window. Blank space is not visible
        or unknown; unknown fraction is shown above.
      </small>
    </div>
  );
}
export function JudgeMode() {
  const generation = useRef(0);
  const [stage, setStage] = useState(0),
    [data, setData] = useState<Dataset | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [active, setActive] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [start, setStart] = useState("2026-11-15T00:00"),
    [duration, setDuration] = useState(168),
    [cadence, setCadence] = useState(60),
    [minimum, setMinimum] = useState(60);
  const [slope, setSlope] = useState(""),
    [roughness, setRoughness] = useState(""),
    [accept, setAccept] = useState(false),
    [mode, setMode] = useState("recorded"),
    [horizon, setHorizon] = useState("GEOMETRIC_IDEAL");
  const [result, setResult] = useState<
      (DelayResponse & { evidence_id: string }) | null
    >(null),
    [analyzed, setAnalyzed] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    call("dataset")
      .then((r) => r.json())
      .then((d: Dataset) => {
        setData(d);
        setActive(d.cells[0]?.cell_id ?? "");
        try {
          const saved = JSON.parse(localStorage.getItem(STORAGE) ?? "null");
          if (saved?.sha === d.dataset_sha256 && Array.isArray(saved.ids)) {
            setSelected([
              ...new Set<string>(
                saved.ids.filter((id: unknown) =>
                  d.cells.some((c) => c.cell_id === id),
                ),
              ),
            ]);
            const s = saved.settings;
            if (s) {
              if (typeof s.start === "string") setStart(s.start);
              if (typeof s.duration === "number") setDuration(s.duration);
              if (typeof s.cadence === "number") setCadence(s.cadence);
              if (typeof s.minimum === "number") setMinimum(s.minimum);
              if (typeof s.slope === "string") setSlope(s.slope);
              if (typeof s.roughness === "string") setRoughness(s.roughness);
              if (typeof s.accept === "boolean") setAccept(s.accept);
              if (["recorded", "configured"].includes(s.mode)) setMode(s.mode);
              if (["GEOMETRIC_IDEAL", "TERRAIN_PARTIAL"].includes(s.horizon))
                setHorizon(s.horizon);
            }
          }
        } catch {
          setNotice("Saved candidates could not be read. Select them again.");
        }
      })
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    if (data)
      try {
        localStorage.setItem(
          STORAGE,
          JSON.stringify({
            sha: data.dataset_sha256,
            dataset: data.metadata,
            ids: selected,
            cells: data.cells.filter((c) => selected.includes(c.cell_id)),
            settings: {
              start,
              duration,
              cadence,
              minimum,
              slope,
              roughness,
              accept,
              mode,
              horizon,
            },
          }),
        );
      } catch {
        setNotice(
          "Browser storage is unavailable. Export your report before leaving.",
        );
      }
  }, [
    selected,
    data,
    start,
    duration,
    cadence,
    minimum,
    slope,
    roughness,
    accept,
    mode,
    horizon,
  ]);
  function change(action: () => void) {
    generation.current++;
    action();
    setResult(null);
    setAnalyzed(null);
    setError("");
  }
  const cell = data?.cells.find((c) => c.cell_id === active);
  function toggle(id: string) {
    change(() =>
      setSelected((v) =>
        v.includes(id) ? v.filter((x) => x !== id) : [...v, id],
      ),
    );
  }
  async function evaluate() {
    if (!data) return;
    const run = ++generation.current;
    setBusy(true);
    setError("");
    setResult(null);
    setAnalyzed(null);
    try {
      if (!accept)
        throw Error(
          "Acknowledge the missing terrain uncertainty before comparing geometry.",
        );
      if (selected.length < 2)
        throw Error("Select at least two source-backed candidate cells.");
      const begin = new Date(start + "Z");
      const request = {
        source_mode: mode,
        dataset_id: data.metadata.dataset_id,
        cell_ids: selected,
        original_cell_id: selected[0],
        start_utc: begin.toISOString(),
        end_utc: new Date(+begin + duration * 3600000).toISOString(),
        step_minutes: cadence,
        minimum_shared_minutes: minimum,
        horizon_model: horizon,
        terrain_site_id: horizon === "TERRAIN_PARTIAL" ? "R04" : null,
        altitude_km: 0,
        observer_height_m: 1,
        filters: {
          qualities: ["source_lola_count_and_uncertainty_not_supplied"],
          maximum_slope_deg: slope === "" ? null : Number(slope),
          maximum_roughness_m: roughness === "" ? null : Number(roughness),
        },
      };
      const r = await call("evaluate", request);
      const value = await r.json();
      if (run !== generation.current) return;
      setResult(value);
      setAnalyzed(request);
      setStage(3);
    } catch (e) {
      if (run === generation.current) setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    if (!analyzed) return;
    setBusy(true);
    setError("");
    try {
      const r = await call("report", { evidence_id: result?.evidence_id });
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "WISPR-research-report.zip";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(
        "Report downloaded: Markdown, summary image and complete evidence.",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const form = (
    <div className="j-form">
      <label>
        Original arrival · UTC
        <input
          type="datetime-local"
          value={start}
          onChange={(e) => change(() => setStart(e.target.value))}
        />
      </label>
      <label>
        Study duration · hours
        <input
          type="number"
          min="1"
          max="744"
          value={duration}
          onChange={(e) => change(() => setDuration(+e.target.value))}
        />
      </label>
      <label>
        Sample cadence · minutes
        <input
          type="number"
          min="1"
          max="1440"
          value={cadence}
          onChange={(e) => change(() => setCadence(+e.target.value))}
        />
      </label>
      <label>
        Required continuous shared window · minutes
        <input
          type="number"
          min="0"
          value={minimum}
          onChange={(e) => change(() => setMinimum(+e.target.value))}
        />
      </label>
      <label>
        Maximum slope · degrees
        <input
          type="number"
          min="0"
          max="90"
          placeholder="No constraint"
          value={slope}
          onChange={(e) => change(() => setSlope(e.target.value))}
        />
      </label>
      <label>
        Maximum roughness · metres
        <input
          type="number"
          min="0"
          placeholder="No constraint"
          value={roughness}
          onChange={(e) => change(() => setRoughness(e.target.value))}
        />
      </label>
      <label>
        Source mode
        <select
          value={mode}
          onChange={(e) => change(() => setMode(e.target.value))}
        >
          <option value="recorded">
            Verified recordings · offline reproducible
          </option>
          <option value="configured">Configured datasets + NASA service</option>
        </select>
      </label>
      <label>
        Horizon model
        <select
          value={horizon}
          onChange={(e) => change(() => setHorizon(e.target.value))}
        >
          <option value="GEOMETRIC_IDEAL">Ideal local horizon</option>
          <option value="TERRAIN_PARTIAL">
            Partial terrain · unsupported stays unknown
          </option>
        </select>
      </label>
      <label className="j-ack">
        <input
          type="checkbox"
          checked={accept}
          onChange={(e) => change(() => setAccept(e.target.checked))}
        />
        I accept missing LOLA shot counts and elevation uncertainty for a
        geometry comparison. This does not establish landing safety.
      </label>
      <p className="j-wide">
        Recorded coverage: November 15–22 and November 22–29, 2026, at 60-minute
        cadence for these two cells. Other requests require matching source
        coverage. Horizons altitude: 0 km above its lunar reference sphere; no
        DEM-height substitution.
      </p>
      <button
        className="j-primary"
        disabled={busy || selected.length < 2 || !accept}
        onClick={evaluate}
      >
        {busy
          ? "Evaluating verified evidence…"
          : "Evaluate original and +7 days"}
      </button>
    </div>
  );
  return (
    <div className="judge">
      <header>
        <a href="/" className="j-brand">
          wispr<span> / LUNAR INTELLIGENCE</span>
        </a>
        <a
          href="#technical"
          onClick={() => setTimeout(() => location.reload(), 0)}
        >
          Technical interface ↗
        </a>
      </header>
      <main>
        <div className="j-title">
          <div>
            <p className="j-kicker">JUDGE PRESENTATION / RESEARCH PROTOTYPE</p>
            <h1>
              The same ground.
              <br />
              <em>A different opportunity.</em>
            </h1>
          </div>
          <p>
            Explore real lunar cells. Compare a seven-day delay. Follow every
            result back to its source.
          </p>
        </div>
        <nav aria-label="Presentation stages">
          {stages.map((name, i) => (
            <button
              key={name}
              aria-current={stage === i ? "step" : undefined}
              className={stage === i ? "active" : ""}
              onClick={() => setStage(i)}
            >
              <small>0{i + 1}</small>
              {name}
            </button>
          ))}
        </nav>
        <section className="j-panel">
          <div className="j-heading">
            <h2>{stages[stage]}</h2>
            <span className="j-status">
              {mode === "recorded"
                ? "RECORDED SOURCE DATA"
                : "CONFIGURED SOURCE REQUEST"}
            </span>
          </div>
          {error && (
            <p role="alert" className="j-error">
              {error}
            </p>
          )}
          {notice && <p role="status">{notice}</p>}
          {!data && !error && (
            <p role="status">Loading source-backed geography…</p>
          )}
          {data && stage === 0 && (
            <div className="j-split">
              <div>
                <p className="j-kicker">NASA LOLA / SHACKLETON RIM / SITE04</p>
                <h3>
                  Two real cells.
                  <br />
                  Their original identities.
                </h3>
                <svg
                  className="j-map"
                  viewBox="-1510 6490 220 120"
                  aria-label="Original NASA-derived Site04 cell footprints in south-polar projected metres"
                >
                  {data.cells.map((c) => (
                    <polygon
                      key={c.cell_id}
                      points={(
                        c.geometry?.coordinates as number[][][] | undefined
                      )?.[0]
                        ?.map(([x, y]) => `${x},${-y}`)
                        .join(" ")}
                      fill={active === c.cell_id ? "#e5c085" : "#497b80"}
                      stroke="#eff4ee"
                      strokeWidth="1"
                      role="button"
                      tabIndex={0}
                      aria-label={`Inspect ${c.cell_id}`}
                      onClick={() => setActive(c.cell_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setActive(c.cell_id);
                        }
                      }}
                    />
                  ))}
                </svg>
                <p>
                  Original projected footprints, not an illustrative lunar
                  photograph. Select a footprint to inspect its coordinates.
                </p>
              </div>
              <article>
                {cell && (
                  <>
                    <h3>{cell.cell_id}</h3>
                    <p>
                      {fmt(cell.latitude_deg)}° latitude ·{" "}
                      {fmt(cell.longitude_deg)}° east-positive longitude
                    </p>
                    <p>
                      NASA LOLA interpolated DEM. Original grid and source
                      measurements are preserved.
                    </p>
                    <a
                      href="https://pgda.gsfc.nasa.gov/products/78"
                      target="_blank"
                      rel="noreferrer"
                    >
                      NASA dataset documentation ↗
                    </a>
                    <button onClick={() => setStage(1)}>
                      Inspect terrain →
                    </button>
                  </>
                )}
              </article>
            </div>
          )}
          {data && stage === 1 && (
            <>
              <p>
                Source-backed measurements describe terrain irregularity at the
                dataset’s scale. Roughness is the RMS residual after fitting a
                plane; slope is the mean native-pixel gradient angle.
              </p>
              <div className="j-cards">
                {data.cells.map((c) => (
                  <article key={c.cell_id}>
                    <h3>{c.cell_id}</h3>
                    <dl>
                      <dt>Mean elevation</dt>
                      <dd>{fmt(c.elevation_m, " m")}</dd>
                      <dt>Mean slope</dt>
                      <dd>{fmt(c.slope_deg, "°")}</dd>
                      <dt>Plane-fit roughness</dt>
                      <dd>{fmt(c.roughness_m, " m")}</dd>
                    </dl>
                    <button onClick={() => toggle(c.cell_id)}>
                      {selected.includes(c.cell_id)
                        ? "Remove candidate"
                        : "Save as candidate"}
                    </button>
                  </article>
                ))}
              </div>
              <p className="j-caution">
                5 m DEM spacing, aggregated into original 100 m cells. Pixel
                spacing is not independent measurement accuracy. Elevation
                uncertainty and laser-shot counts are unknown. No landing-safety
                claim.
              </p>
            </>
          )}
          {data && stage === 2 && (
            <>
              <p>
                Choose two real cells. The first selected cell is the original
                location. Candidates retain the dataset hash, coordinates,
                source version and current settings in this browser.
              </p>
              <div className="j-cards">
                {data.cells.map((c) => (
                  <label className="j-candidate" key={c.cell_id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(c.cell_id)}
                      onChange={() => toggle(c.cell_id)}
                    />
                    <strong>{c.cell_id}</strong>
                    <span>
                      {fmt(c.latitude_deg)}°, {fmt(c.longitude_deg)}° E
                    </span>
                    <small>
                      {selected[0] === c.cell_id
                        ? "Original location"
                        : "Comparison candidate"}
                    </small>
                  </label>
                ))}
              </div>
              {form}
            </>
          )}
          {stage === 3 &&
            (result ? (
              <>
                <p className="j-caution">
                  Equal{" "}
                  {(Date.parse(result.original.scenario.end_utc) -
                    Date.parse(result.original.scenario.start_utc)) /
                    3600000}
                  -hour study durations · exact +7-day shift ·{" "}
                  {result.original.scenario.step_minutes} minute cadence ·{" "}
                  {result.original.scenario.horizon_model}. A full-window value
                  is capped by the analysis duration.
                </p>
                <div className="j-cards j-comparison">
                  {(["original", "delayed"] as const).map((name) => (
                    <article key={name}>
                      <p className="j-kicker">
                        {name === "original" ? "ORIGINAL ARRIVAL" : "+7 DAYS"}
                      </p>
                      <p>
                        {result[name].scenario.start_utc} →{" "}
                        {result[name].scenario.end_utc}
                      </p>
                      {result[name].results.map((row) => {
                        const d = row.dynamic_vector;
                        const hours =
                          d?.features.longest_shared_minutes == null
                            ? null
                            : d.features.longest_shared_minutes / 60;
                        const full =
                          d &&
                          hours != null &&
                          Math.abs(
                            hours -
                              (Date.parse(d.end_utc) -
                                Date.parse(d.start_utc)) /
                                3600000,
                          ) < 1e-6;
                        return (
                          <div className="j-result" key={row.cell_id}>
                            <h3>{row.cell_id}</h3>
                            <strong className="j-number">
                              {fmt(hours)}
                              <small>{hours == null ? "" : " h"}</small>
                            </strong>
                            <p>
                              Longest continuous shared visibility
                              {full ? " · full-window cap" : ""}
                            </p>
                            {d ? (
                              <>
                                <small>
                                  {d.quality.replaceAll("_", " ")} ·{" "}
                                  {fmt(d.features.unknown_data_fraction * 100)}%
                                  unknown
                                </small>
                                <Windows d={d} />
                              </>
                            ) : (
                              <p className="j-error">
                                Unknown / not evaluated:{" "}
                                {(row.reasons ?? []).join(", ")}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </article>
                  ))}
                </div>
                <p>
                  Sun visibility is not electrical power availability. Earth
                  visibility is not an operational radio link. Cell differences
                  below one cadence do not establish a meaningful advantage.
                </p>
              </>
            ) : (
              <div className="j-empty">
                <h3>Calculate before comparing.</h3>
                <p>
                  No illustrative numbers or empty charts are substituted for
                  evidence.
                </p>
                <button onClick={() => setStage(2)}>
                  Choose candidates and inputs →
                </button>
              </div>
            ))}
          {stage === 4 && (
            <>
              {result && (
                <article className="j-decision">
                  <p className="j-kicker">DETERMINISTIC CONSTRAINT CHECK</p>
                  <h3>{result.outcome}</h3>
                  <p>{result.reason}</p>
                  <p>{result.delayed.comparison.significance_warning}</p>
                  <ul>
                    {result.delayed.comparison.ranked.map((c) => (
                      <li key={c.cell_id}>
                        {c.cell_id} · {fmt(c.longest_shared_minutes / 60)} h ·
                        meets supplied constraints
                      </li>
                    ))}
                    {result.delayed.comparison.excluded.map((c) => (
                      <li key={c.cell_id}>
                        {c.cell_id} · excluded: {c.reasons.join(", ")}
                      </li>
                    ))}
                  </ul>
                </article>
              )}
              <p>
                Change the arrival date or screening constraints and reevaluate.
                Candidate changes are available in “Compare Candidates.”
                Unsupported dates or terrain remain unknown; no later
                opportunity is inferred.
              </p>
              {form}
            </>
          )}
          {stage === 5 && (
            <div className="j-split">
              <div>
                <h3>
                  A readable report.
                  <br />
                  An inspectable scientific record.
                </h3>
                <p>
                  Download a ZIP containing a Markdown report, a comparison
                  summary SVG and complete JSON evidence. The report records
                  actual inputs, source hashes, intervals, exclusions and model
                  assumptions.
                </p>
                <button
                  className="j-primary"
                  onClick={download}
                  disabled={!result || busy}
                >
                  {busy ? "Preparing report…" : "Download research report"}
                </button>
                {!result && <p>Evaluate a comparison first.</p>}
              </div>
              <article>
                <h3>What AI does here</h3>
                <p>
                  The current repository supports Groq and NVIDIA for
                  schema-validated mission input extraction in the technical
                  interface. Provider status: {data?.ai_status ?? "Unknown"}.
                </p>
                <p>
                  This presentation uses a deterministic manual form and factual
                  report. No embedding retrieval or Gemini integration is
                  claimed by this branch. AI never supplies missing physical
                  measurements.
                </p>
              </article>
            </div>
          )}
          {data && (
            <details className="j-method">
              <summary>
                Methodology, source versions and exact provenance
              </summary>
              <p>{data.note}</p>
              <p>
                Target centers must be above the chosen horizon. Crossing times
                are piecewise-linear estimates between adjacent samples; missing
                intervals remain unknown. Printed decimal precision is not a
                timing uncertainty estimate. Cadence limits interpretation.
              </p>
              <p>
                MOON_ME / DE421; east-positive longitude; UTC; airless apparent
                geometry. DEM/Horizons vertical alignment and distant terrain
                obstruction are unresolved.
              </p>
              <p>
                Dataset SHA-256: <code>{data.dataset_sha256}</code>
              </p>
              <pre>{JSON.stringify(result ?? data, null, 2)}</pre>
            </details>
          )}
        </section>
        <div className="j-next">
          <button disabled={stage === 0} onClick={() => setStage((s) => s - 1)}>
            ← Previous
          </button>
          <span>
            {stage + 1} / {stages.length}
          </span>
          <button disabled={stage === 5} onClick={() => setStage((s) => s + 1)}>
            Next →
          </button>
        </div>
        <footer>
          WISPR / NASA SPACE APPS PROTOTYPE · Not flight-qualified or
          NASA-approved.
        </footer>
      </main>
    </div>
  );
}
