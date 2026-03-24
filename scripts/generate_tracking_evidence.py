from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_FIXED_TIMESTAMP = "2026-03-24T23:30:00Z"


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "tracking" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible Section 5 tracking-and-fusion benchmark evidence.",
    )
    parser.add_argument("--output-root", default="services/tracking/fixtures")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_tracking import benchmark_tracking_strategies

    args = parse_args()
    output_root = (repo_root / args.output_root).resolve() if not Path(args.output_root).is_absolute() else Path(args.output_root).resolve()
    report_path = output_root / "reports" / "tracking-strategy-benchmark.json"
    if report_path.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite existing report without --overwrite: {report_path}")

    report = benchmark_tracking_strategies(generated_at_utc=_FIXED_TIMESTAMP)
    _write_json(report_path, report.model_dump(mode="json"))

    crowded = report.algorithms["byte_tracker"].scenarios["crowded_crossing"]
    motion = report.algorithms["byte_tracker"].scenarios["camera_motion_drift"]
    repeated = report.algorithms["byte_tracker"].scenarios["repeat_pass_duplicate_window"]

    print(f"Tracking evidence root: {output_root}")
    print(f"Report: {report_path}")
    print(f"Recommended algorithm: {report.recommended_algorithm.value}")
    print(
        "Byte tracker baseline: "
        f"crowded_crossing plate_exact_matches={crowded.plate_exact_matches}, "
        f"camera_motion finalized={motion.finalized_detections}, "
        f"repeat_pass suppressed_duplicates={repeated.suppressed_duplicates}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
