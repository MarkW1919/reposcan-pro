from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "ml" / "training" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qualify an approved eval-holdout dataset for night / long-range regression use.")
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--min-total-assets", type=int, default=10)
    parser.add_argument("--min-benchmark-ready-assets", type=int, default=10)
    parser.add_argument("--min-long-range-assets", type=int, default=4)
    parser.add_argument("--min-low-light-assets", type=int, default=4)
    parser.add_argument("--min-long-range-sessions", type=int, default=2)
    parser.add_argument("--min-low-light-sessions", type=int, default=2)
    parser.add_argument("--allow-missing-expected-plate-text", action="store_true")
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--report-output")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _resolve_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest
    from reposcan_contracts.field_eval import FieldEvalCoveragePolicy
    from reposcan_training import qualify_field_eval_dataset

    args = parse_args()
    manifest_path = _resolve_path(repo_root, args.dataset_manifest)
    report_output = _resolve_path(repo_root, args.report_output) if args.report_output else None

    manifest = load_training_dataset_manifest(manifest_path)
    policy = FieldEvalCoveragePolicy(
        min_total_assets=args.min_total_assets,
        min_benchmark_ready_assets=args.min_benchmark_ready_assets,
        min_long_range_assets=args.min_long_range_assets,
        min_low_light_assets=args.min_low_light_assets,
        min_long_range_sessions=args.min_long_range_sessions,
        min_low_light_sessions=args.min_low_light_sessions,
        require_expected_plate_text=not args.allow_missing_expected_plate_text,
        verify_files=args.verify_files,
    )
    report = qualify_field_eval_dataset(repo_root=repo_root, manifest=manifest, policy=policy)

    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Dataset: {report.dataset_name}")
        print(f"Qualified: {report.qualified}")
        print(f"Total assets: {report.total_assets}")
        print(f"Benchmark-ready assets: {report.benchmark_ready_assets}")
        print(f"Long-range assets: {report.subsets['long_range'].assets}")
        print(f"Low-light assets: {report.subsets['low_light'].assets}")
        if report_output is not None:
            print(f"Report output: {report_output}")
        if report.issues:
            print("Issues:")
            for issue in report.issues:
                print(f"- {issue.severity}: [{issue.scope}] {issue.message}")

    return 0 if report.qualified else 1


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
