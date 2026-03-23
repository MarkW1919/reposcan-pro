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
    parser = argparse.ArgumentParser(description="Register a validated promoted bundle into an external release registry.")
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--deployment-config", required=True)
    parser.add_argument("--benchmark-manifest", required=True)
    parser.add_argument("--registry-root", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--release-id")
    parser.add_argument("--notes")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_inference import register_model_release

    args = parse_args()
    report = register_model_release(
        model_config_path=_resolve_path(repo_root, args.model_config),
        deployment_config_path=_resolve_path(repo_root, args.deployment_config),
        benchmark_manifest_path=_resolve_path(repo_root, args.benchmark_manifest),
        registry_root=_resolve_path(repo_root, args.registry_root),
        channel_name=args.channel,
        pipeline_config_path=_resolve_path(repo_root, args.pipeline_config),
        release_id=args.release_id,
        notes=args.notes,
    )

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Registered release: {report.release.release_id}")
        print(f"Channel: {report.channel.channel_name}")
        print(f"Current release: {report.channel.current_release_id}")
        print(f"Previous release: {report.channel.previous_release_id}")
        print(f"Benchmark exact match: {report.release.overall_benchmark.exact_match_rate}")
        print(f"Benchmark character accuracy: {report.release.overall_benchmark.character_accuracy}")
        print(f"Release record: {report.release_record_path}")
        print(f"Channel file: {report.channel_path}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
