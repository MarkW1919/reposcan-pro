from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "apps" / "api" / "src",
        repo_root / "services" / "storage" / "src",
        repo_root / "services" / "capture" / "src",
        repo_root / "services" / "preprocessing" / "src",
        repo_root / "services" / "inference" / "src",
        repo_root / "services" / "tracking" / "src",
        repo_root / "services" / "alerting" / "src",
        repo_root / "services" / "sync" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the RepoScan Pro internet-outage local-first acceptance harness. "
            "Drives a realistic capture->storage->alerting->sync flow with all "
            "outbound transports forced offline, checks the local-first "
            "invariants hold, then restores the transports and verifies that "
            "the queued state drains cleanly on recovery."
        ),
    )
    parser.add_argument(
        "--deployment-config",
        default="configs/deployments/local-dev.yaml",
        help="Deployment config that selects the storage backend for the run.",
    )
    parser.add_argument(
        "--pipeline-config",
        default="configs/pipelines/default-edge.yaml",
        help="Pipeline config used by the alerting service for threshold evaluation.",
    )
    parser.add_argument(
        "--detection-count",
        type=int,
        default=10,
        help="Number of synthetic detections to drive through the flow.",
    )
    parser.add_argument(
        "--hotlist-plate",
        default="HOTLIST1",
        help="Plate text used for the hotlist entry; the first detection matches it.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/acceptance/outage",
        help="Directory that holds per-run outage acceptance output folders.",
    )
    parser.add_argument(
        "--workspace-root",
        help="Workspace directory for the in-process storage + queue. Defaults to <output-root>/<run-id>/workspace.",
    )
    parser.add_argument(
        "--run-id",
        help="Explicit outage run id. A UTC timestamped id is generated if omitted.",
    )
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_sync import (
        default_outage_run_id,
        run_internet_outage_acceptance,
        write_outage_artifacts,
    )

    args = parse_args()
    output_root = _resolve_path(repo_root, args.output_root)
    assert output_root is not None

    run_id = args.run_id or default_outage_run_id()
    workspace_root = _resolve_path(repo_root, args.workspace_root) or (output_root / run_id / "workspace")

    report = run_internet_outage_acceptance(
        workspace_root=workspace_root,
        run_id=run_id,
        deployment_config_path=str(_resolve_path(repo_root, args.deployment_config)),
        pipeline_config_path=str(_resolve_path(repo_root, args.pipeline_config)),
        detection_count=args.detection_count,
        hotlist_plate=args.hotlist_plate,
    )
    run_dir = write_outage_artifacts(report, output_root=output_root)

    print(f"Outage acceptance run: {run_id}")
    print(f"Output: {run_dir}")
    print(f"Deployment: {report.deployment_name}")
    print(f"Detections ingested: {report.detections_ingested}")
    print(f"Overall result: {'PASS' if report.passed else 'FAIL'}")
    for inv in report.invariants:
        status = "PASS" if inv.passed else "FAIL"
        print(f"- [{status}] {inv.phase}: {inv.name}")
        if not inv.passed and inv.detail:
            print(f"    {inv.detail}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
