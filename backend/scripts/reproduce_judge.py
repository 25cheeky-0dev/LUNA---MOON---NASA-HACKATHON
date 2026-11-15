"""Recompute the documented two-cell comparison from authentic recorded NASA data."""

import argparse
import json
from pathlib import Path

from app.judge import JudgeRequest, calculate, recorded, report_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    output = Path(parser.parse_args().output)
    d, _ = recorded()
    request = JudgeRequest(
        dataset_id=d.metadata.dataset_id,
        cell_ids=[c.cell_id for c in d.cells],
        original_cell_id=d.cells[0].cell_id,
        start_utc="2026-11-15T00:00:00Z",
        end_utc="2026-11-22T00:00:00Z",
        step_minutes=60,
        minimum_shared_minutes=60,
        filters={"qualities": ["source_lola_count_and_uncertainty_not_supplied"]},
    )
    result = calculate(request)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in report_files(result, request).items():
        (output / name).write_bytes(content)
    (output / "request.json").write_text(
        json.dumps(request.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "source_mode": request.source_mode,
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
