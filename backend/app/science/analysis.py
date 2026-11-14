import hashlib
import json
from app.metadata import iso, metadata
from app.schemas import EphemerisRequest
from app.providers.horizons import SourceUnavailable
from app.science.windows import summarize


async def analyze_scenario(site_id, start, end, request, provider):
    identity = dict(site_id=site_id, start=iso(start), end=iso(end), horizon_model=request.horizon_model,
        observer_height_m=request.observer_height_m, step_minutes=request.step_minutes,
        minimum=request.min_continuous_overlap_minutes, engine='linear-v1')
    scenario_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    base = dict(scenario_id=scenario_id, site_id=site_id, arrival_utc=iso(start), end_utc=iso(end),
        horizon_model=request.horizon_model, observer_height_m=request.observer_height_m,
        observation_point_type='REFERENCE_SITE', cell_id=None)
    if request.horizon_model == 'LOCAL_TERRAIN':
        error = 'TERRAIN_HORIZON_INCOMPLETE_OR_UNAVAILABLE'
    else:
        try:
            eph = await provider.ephemeris(EphemerisRequest(site_id=site_id, start_utc=start, end_utc=end,
                step_minutes=request.step_minutes, observer_height_m=request.observer_height_m))
            meta = {k: eph[k] for k in metadata()}
            summary = summarize(eph['records'], start, end, request.step_minutes, request.min_continuous_overlap_minutes)
            result = dict(**base, **summary, visibility_series=eph['records'], **meta)
            result['data_quality'] = 'MODEL_ESTIMATE' if summary['qualifying_status'] != 'UNKNOWN' else 'PARTIAL'
            result['time_to_first_qualifying_minutes'] = (
                (__import__('datetime').datetime.fromisoformat(summary['earliest_qualifying_window']['start_utc'].replace('Z','+00:00'))-start).total_seconds()/60
                if summary['earliest_qualifying_window'] else None)
            return result
        except SourceUnavailable as exc:
            error = str(exc)
    return dict(**base, sun_windows=[], earth_windows=[], shared_windows=[], longest_shared_minutes=None,
        earliest_qualifying_window=None, known_fraction=0., unknown_fraction=1., qualifying_status='UNKNOWN',
        reason_codes=[error], visibility_series=[], unknown_intervals=[dict(start_utc=iso(start), end_utc=iso(end), reason=error)],
        time_to_first_qualifying_minutes=None, metrics={},
        **metadata(mode='TERRAIN_UNAVAILABLE' if request.horizon_model == 'LOCAL_TERRAIN' else 'GEOMETRIC_IDEAL', limitations=[error]))
