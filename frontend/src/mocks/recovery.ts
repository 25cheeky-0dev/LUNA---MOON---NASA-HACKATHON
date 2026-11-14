import type { MissionRequest, Outcome, Recovery, Scenario, Sky, Window } from '../lib/api';
const source = { source_type: 'SYNTHETIC_TEST_ONLY', calculation_mode: 'GEOMETRIC_IDEAL', data_quality: 'SYNTHETIC_TEST_ONLY', provenance: { source_urls: [], raw_sha256: [] }, limitations: ['SYNTHETIC EXAMPLE — NOT NASA DATA'] };
function sky(el: number, az: number): Sky { const a = az * Math.PI/180, e = el * Math.PI/180; return { az_deg: az, el_deg: el, east: Math.cos(e)*Math.sin(a), north: Math.cos(e)*Math.cos(a), up: Math.sin(e), status: 'KNOWN' }; }
export function fixture(request: MissionRequest, outcome: Outcome): Recovery {
  const original = new Date(request.original_arrival_utc ?? '2026-11-20T00:00:00Z');
  const duration = request.study_duration_hours ?? 24;
  const scenario = (site: 'R01' | 'R04', delayed: boolean): Scenario => {
    const start = new Date(+original + (delayed ? 168 : 0)*3600000);
    const end = new Date(+start + duration*3600000);
    const unknown = outcome === 'INSUFFICIENT_DATA' || request.horizon_model === 'LOCAL_TERRAIN';
    const passes = !unknown && (outcome === 'KEEP_SITE_AFTER_DELAY' ? site === request.original_site_id : outcome === 'SWITCH_SITE_AFTER_DELAY' ? site !== request.original_site_id : !delayed);
    const length = Math.min(duration*60, passes ? 240 : 120);
    const w: Window = { start_utc: start.toISOString(), end_utc: new Date(+start+length*60000).toISOString(), duration_minutes: length, kind: 'BOTH', estimate_status: 'MODEL_ESTIMATE', boundary_uncertainty_seconds: 300, model: 'GEOMETRIC_IDEAL' };
    return { ...source, scenario_id: `SYNTHETIC-${site}-${delayed}`, site_id: site, arrival_utc: start.toISOString(), end_utc: end.toISOString(), horizon_model: request.horizon_model,
      sun_windows: unknown ? [] : [{...w,kind:'SUN'}], earth_windows: unknown ? [] : [{...w,kind:'EARTH'}], shared_windows: unknown ? [] : [w], longest_shared_minutes: unknown ? null : length,
      earliest_qualifying_window: passes && length >= request.min_continuous_overlap_minutes ? w : null, known_fraction: unknown ? 0 : 1, unknown_fraction: unknown ? 1 : 0,
      qualifying_status: unknown ? 'UNKNOWN' : passes && length >= request.min_continuous_overlap_minutes ? 'QUALIFIES' : 'FAILS', reason_codes: unknown ? ['SYNTHETIC_MISSING_DATA'] : passes ? [] : ['SYNTHETIC_NO_QUALIFYING_WINDOW'], time_to_first_qualifying_minutes: passes ? 0 : null,
      unknown_intervals: unknown ? [{start_utc:start.toISOString(),end_utc:end.toISOString(),reason:'SYNTHETIC_UNKNOWN'}] : [],
      visibility_series: Array.from({length: Math.floor(duration*12)+1},(_,i) => ({timestamp_utc:new Date(+start+i*300000).toISOString(),sun:unknown?null:sky(i*5<length?2:-1, (120+i*.12)%360),earth:unknown?null:sky(1,220),status:unknown?'UNKNOWN' as const:'KNOWN' as const,gap_reason:unknown?'SYNTHETIC_UNKNOWN':null})) };
  };
  const originals = [scenario('R01',false),scenario('R04',false)], delayed = [scenario('R01',true),scenario('R04',true)];
  const future = outcome === 'POSTPONE_AND_REEVALUATE' ? [{...delayed[0],scenario_id:'SYNTHETIC-FUTURE',arrival_utc:new Date(+original+192*3600000).toISOString(),end_utc:new Date(+original+(192+duration)*3600000).toISOString(),visibility_series:[],qualifying_status:'QUALIFIES' as const,earliest_qualifying_window:{...delayed[0].shared_windows[0],start_utc:new Date(+original+192*3600000).toISOString(),end_utc:new Date(+original+196*3600000).toISOString(),duration_minutes:240}}] : [];
  const picked = future[0] ?? delayed.find(s=>s.qualifying_status==='QUALIFIES');
  return {...source,request,original_scenarios: originals,delayed_scenarios:delayed,future_scenarios:future,ranked_eligible:[...delayed,...future].filter(s=>s.qualifying_status==='QUALIFIES'),recommended_outcome:unknownOutcome(),recommended_site_id:picked?.site_id??null,recommended_window:picked?.earliest_qualifying_window??null,
    recommendation_reason:'Synthetic interface example. No lunar conditions have been calculated.',missing_fields:outcome==='NEEDS_INPUT'?['original_arrival_utc']:[],search_scope:{original_arrival_utc:original.toISOString(),delayed_arrival_utc:new Date(+original+168*3600000).toISOString(),study_duration_hours:duration,future_search_days:request.future_search_days},rejections:[],unknowns:[],scientific_disclaimer:'SYNTHETIC EXAMPLE — NOT NASA DATA'};
  function unknownOutcome() { return request.horizon_model==='LOCAL_TERRAIN' ? 'INSUFFICIENT_DATA' as const : outcome; }
}
