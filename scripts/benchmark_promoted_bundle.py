from __future__ import annotations

import argparse
import json
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
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark a promoted runtime bundle against a tagged frame manifest.")
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--benchmark-manifest", required=True)
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_benchmark_manifest
    from reposcan_inference import InferenceService
    from reposcan_inference.benchmarking import benchmark_promoted_model

    args = parse_args()
    inference_service = InferenceService.from_config_paths(
        model_config_path=repo_root / args.model_config,
        pipeline_config_path=repo_root / args.pipeline_config,
    )
    manifest = load_benchmark_manifest(repo_root / args.benchmark_manifest)
    report = benchmark_promoted_model(inference_service, manifest)

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Benchmark: {report.benchmark_name}")
        print(f"Model stack: {report.model_stack_name}")
        print(f"Overall exact match: {report.overall.exact_match_rate}")
        print(f"Overall character accuracy: {report.overall.character_accuracy}")
        for subset_name, metrics in report.subsets.items():
            print(
                f"- {subset_name}: exact_match={metrics.exact_match_rate}, "
                f"character_accuracy={metrics.character_accuracy}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
