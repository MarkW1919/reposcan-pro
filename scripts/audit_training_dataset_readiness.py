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
    parser = argparse.ArgumentParser(
        description="Audit a RepoScan training dataset manifest against an Oklahoma production-readiness gate."
    )
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument(
        "--level",
        default="oklahoma-commercial",
        choices=["warmstart", "development", "production-candidate", "commercial-grade", "oklahoma-commercial"],
        help="Readiness gate to apply. Defaults to the Oklahoma commercial shipping gate.",
    )
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
    from reposcan_training import audit_dataset_readiness, build_dataset_readiness_policy

    args = parse_args()
    manifest_path = _resolve_path(repo_root, args.dataset_manifest)
    report_output = _resolve_path(repo_root, args.report_output) if args.report_output else None

    manifest = load_training_dataset_manifest(manifest_path)
    policy = build_dataset_readiness_policy(args.level)
    policy.verify_files = args.verify_files
    report = audit_dataset_readiness(repo_root=repo_root, manifest=manifest, policy=policy)
    payload = report.model_dump(mode="json")

    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Dataset: {report.dataset_name}")
        print(f"Task: {report.task.value}")
        print(f"Policy: {report.policy_name}")
        print(f"Ready: {report.ready}")
        print(f"Total samples: {report.total_samples}")
        print(f"Split samples: {report.split_samples}")
        print(f"Capture sessions: {report.capture_sessions}")
        print(f"Low-light assets: {report.low_light_assets}")
        print(f"Long-range assets: {report.long_range_assets}")
        print(f"Synthetic train samples: {report.synthetic_train_samples}")
        if report_output is not None:
            print(f"Report output: {report_output}")
        if report.issues:
            print("Issues:")
            for issue in report.issues:
                print(f"- {issue.severity}: [{issue.scope}] {issue.message}")

    return 0 if report.ready else 1


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
