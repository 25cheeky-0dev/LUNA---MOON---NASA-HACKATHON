"""Reuse sampled geometric windows; partial terrain never certifies clearance."""

from app.science.windows import summarize


def visibility(ephemeris, request, terrain_profile):
    records, statuses = [], []
    for row in ephemeris.records:
        positions = {}
        for body in ("sun", "earth"):
            elevation = getattr(row, f"{body}_elevation_deg")
            positions[body] = None if elevation is None else dict(el_deg=elevation, status="KNOWN")
        records.append(
            dict(timestamp_utc=row.timestamp_utc.isoformat().replace("+00:00", "Z"), **positions)
        )
        statuses.append(
            dict(
                timestamp_utc=records[-1]["timestamp_utc"],
                geometric={
                    body: "UNKNOWN"
                    if positions[body] is None
                    else "ABOVE_IDEAL_HORIZON"
                    if positions[body]["el_deg"] > 0
                    else "NOT_ABOVE_IDEAL_HORIZON"
                    for body in ("sun", "earth")
                },
                terrain={body: "UNKNOWN" for body in ("sun", "earth")},
                terrain_reason="DEM_OBSERVER_HEIGHT_REFERENCE_UNRECONCILED_AND_LOCAL_COVERAGE_INCOMPLETE",
            )
        )
    interval = ephemeris.metadata["request"]
    from app.metadata import parse

    summary = summarize(
        records,
        parse(interval["start_utc"]),
        parse(interval["end_utc"]),
        request.step_minutes,
        request.min_shared_window_minutes,
    )
    return dict(
        model="GEOMETRIC_IDEAL_LINEAR_V1",
        quality="MODEL_ESTIMATE",
        samples=statuses,
        geometric_window_summary=summary,
        terrain_profile=terrain_profile,
        terrain_visibility="UNKNOWN",
        terrain_known_fraction=0.0,
        interpretation="Sampled apparent target-center geometry; not solar disk, power or radio-link availability",
    )
