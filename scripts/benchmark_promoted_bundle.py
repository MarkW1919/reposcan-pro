from __future__ import annotations

import argparse
import json
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
    parser = argparse.ArgumentParser(description="Benchmark a promoted runtime bundle against a benchmark manifest or eval-holdout dataset.")
    parser.add_argument("--model-config", required=True)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--benchmark-manifest")
    source_group.add_argument("--dataset-manifest")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--deployment-config")
    parser.add_argument("--benchmark-name")
    parser.add_argument("--camera-id")
    parser.add_argument("--derived-benchmark-output")
    parser.add_argument("--report-output")
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
        build_benchmark_manifest_from_eval_holdout,
    )

    args = parse_args()
    model_config_path = _resolve_path(repo_root, args.model_config)
    pipeline_config_path = _resolve_path(repo_root, args.pipeline_config)
    deployment_config_path = _resolve_path(repo_root, args.deployment_config)
    benchmark_manifest_path = _resolve_path(repo_root, args.benchmark_manifest)
    dataset_manifest_path = _resolve_path(repo_root, args.dataset_manifest)
    derived_benchmark_output = _resolve_path(repo_root, args.derived_benchmark_output)
    report_output = _resolve_path(repo_root, args.report_output)

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
        if derived_benchmark_output is not None:
            _write_yaml(derived_benchmark_output, manifest.model_dump(mode="json", exclude_none=True))
    else:
        manifest = load_benchmark_manifest(benchmark_manifest_path)
        if args.benchmark_name:
            manifest.benchmark_name = args.benchmark_name
        if args.camera_id:
            manifest.camera_id = args.camera_id

    deployment = load_deployment_config(deployment_config_path) if deployment_config_path is not None else None
    report = benchmark_promoted_model(
        inference_service,
        manifest,
        deployment=deployment,
        benchmark_manifest_path=benchmark_manifest_path if dataset_manifest_path is None else derived_benchmark_output,
        source_dataset_manifest=source_dataset_manifest,
        source_dataset_manifest_path=dataset_manifest_path,
    )

    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Benchmark: {report.benchmark_name}")
        print(f"Model stack: {report.model_stack_name}")
        if report.source_dataset_name:
            print(f"Source dataset: {report.source_dataset_name} ({report.source_dataset_version})")
        print(f"Overall exact match: {report.overall.exact_match_rate}")
        print(f"Overall character accuracy: {report.overall.character_accuracy}")
        print(f"Overall average latency ms: {report.overall.average_latency_ms}")
        if report.validation is not None:
            print(f"Runtime ready: {report.validation.runtime_ready}")
            print(f"Promotion ready: {report.validation.promotion_ready}")
            if report.validation.deployment_ready is not None:
                print(f"Deployment ready: {report.validation.deployment_ready}")
        for subset_name, metrics in report.subsets.items():
            print(
                f"- {subset_name}: exact_match={metrics.exact_match_rate}, "
                f"character_accuracy={metrics.character_accuracy}, "
                f"average_latency_ms={metrics.average_latency_ms}"
            )
        if derived_benchmark_output is not None:
            print(f"Derived benchmark manifest: {derived_benchmark_output}")
        if report_output is not None:
            print(f"Report output: {report_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
