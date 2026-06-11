from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


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
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a RepoScan Pro acceptance evaluation against a promoted runtime bundle "
            "and a field eval-holdout (or an explicit benchmark manifest). Produces "
            "long-range, low-light, and moving-platform lane reports for the "
            "production-readiness review register."
        ),
    )
    parser.add_argument("--model-config", required=True, help="Path to the promoted model stack config.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--dataset-manifest", help="Field eval-holdout dataset manifest path.")
    source_group.add_argument("--benchmark-manifest", help="Pre-built benchmark manifest path.")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--deployment-config")
    parser.add_argument("--benchmark-name")
    parser.add_argument("--camera-id")
    parser.add_argument(
        "--output-root",
        default="artifacts/acceptance",
        help="Directory that holds per-run acceptance output folders.",
    )
    parser.add_argument(
        "--run-id",
        help="Explicit acceptance run id. A UTC timestamped id is generated if omitted.",
    )
    parser.add_argument(
        "--derived-benchmark-output",
        help="Optional path to persist the lane-stamped benchmark manifest for audit.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _git_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import (
        load_benchmark_manifest,
        load_deployment_config,
        load_training_dataset_manifest,
    )
    from reposcan_inference import (
        InferenceService,
        benchmark_promoted_model,
        build_acceptance_run_report,
        build_benchmark_manifest_from_eval_holdout,
        default_run_id,
        stamp_acceptance_lanes,
        write_acceptance_artifacts,
    )

    args = parse_args()
    model_config_path = _resolve_path(repo_root, args.model_config)
    pipeline_config_path = _resolve_path(repo_root, args.pipeline_config)
    deployment_config_path = _resolve_path(repo_root, args.deployment_config)
    benchmark_manifest_path = _resolve_path(repo_root, args.benchmark_manifest)
    dataset_manifest_path = _resolve_path(repo_root, args.dataset_manifest)
    derived_benchmark_output = _resolve_path(repo_root, args.derived_benchmark_output)
    output_root = _resolve_path(repo_root, args.output_root)

    inference_service = InferenceService.from_config_paths(
        model_config_path=model_config_path,
        pipeline_config_path=pipeline_config_path,
    )

    source_dataset_manifest = None
    if dataset_manifest_path is not None:
        source_dataset_manifest = load_training_dataset_manifest(dataset_manifest_path)
        manifest = build_benchmark_manifest_from_eval_holdout(
            repo_root=repo_root,
            dataset_manifest=source_dataset_manifest,
            dataset_manifest_path=dataset_manifest_path,
            benchmark_name=args.benchmark_name,
            camera_id=args.camera_id,
        )
    else:
        manifest = load_benchmark_manifest(benchmark_manifest_path)
        if args.benchmark_name:
            manifest.benchmark_name = args.benchmark_name
        if args.camera_id:
            manifest.camera_id = args.camera_id

    stamped_manifest = stamp_acceptance_lanes(manifest)
    if derived_benchmark_output is not None:
        _write_yaml(derived_benchmark_output, stamped_manifest.model_dump(mode="json", exclude_none=True))

    deployment = load_deployment_config(deployment_config_path) if deployment_config_path is not None else None
    benchmark_report = benchmark_promoted_model(
        inference_service,
        stamped_manifest,
        deployment=deployment,
        benchmark_manifest_path=benchmark_manifest_path if dataset_manifest_path is None else derived_benchmark_output,
        source_dataset_manifest=source_dataset_manifest,
        source_dataset_manifest_path=dataset_manifest_path,
    )

    run_id = args.run_id or default_run_id()
    acceptance_report = build_acceptance_run_report(benchmark_report, run_id=run_id)
    assert output_root is not None
    run_dir = write_acceptance_artifacts(acceptance_report, output_root=output_root)

    benchmark_sidecar = run_dir / "benchmark_report.json"
    benchmark_sidecar.write_text(
        json.dumps(benchmark_report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    run_manifest = {
        "run_id": run_id,
        "generated_at_utc": acceptance_report.generated_at_utc,
        "git_head": _git_head(repo_root),
        "model_config": str(model_config_path) if model_config_path else None,
        "pipeline_config": str(pipeline_config_path) if pipeline_config_path else None,
        "deployment_config": str(deployment_config_path) if deployment_config_path else None,
        "dataset_manifest": str(dataset_manifest_path) if dataset_manifest_path else None,
        "benchmark_manifest": str(benchmark_manifest_path) if benchmark_manifest_path else None,
        "derived_benchmark_manifest": str(derived_benchmark_output) if derived_benchmark_output else None,
        "model_stack_name": benchmark_report.model_stack_name,
        "benchmark_name": benchmark_report.benchmark_name,
        "lanes": [
            {"lane": lane.lane, "status": lane.status, "frames": lane.frames}
            for lane in acceptance_report.lanes
        ],
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(acceptance_report.model_dump(mode="json"), indent=2))
    else:
        print(f"Acceptance run: {run_id}")
        print(f"Output: {run_dir}")
        print(f"Model stack: {acceptance_report.model_stack_name}")
        if acceptance_report.source_dataset_name:
            version = acceptance_report.source_dataset_version or "n/a"
            print(f"Source dataset: {acceptance_report.source_dataset_name} ({version})")
        print(
            "Overall: "
            f"exact_match={acceptance_report.overall.exact_match_rate}, "
            f"char_accuracy={acceptance_report.overall.character_accuracy}, "
            f"frames={acceptance_report.overall.frames}"
        )
        for lane in acceptance_report.lanes:
            metrics = lane.metrics
            if metrics is None:
                print(f"- {lane.lane}: {lane.status} (frames={lane.frames})")
            else:
                print(
                    f"- {lane.lane}: {lane.status} "
                    f"(frames={metrics.frames}, exact_match={metrics.exact_match_rate})"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
