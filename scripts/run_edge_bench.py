from __future__ import annotations

import argparse
import json
import subprocess
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
    parser = argparse.ArgumentParser(
        description=(
            "Run the RepoScan Pro edge inference bench harness. Produces "
            "per-stage latency, cold-start, peak memory, and thermal samples "
            "for the production-readiness review register."
        ),
    )
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--deployment-config")
    parser.add_argument(
        "--benchmark-manifest",
        required=True,
        help="Benchmark manifest whose frames drive the bench (re-use any promoted-bundle manifest).",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/bench/edge",
        help="Directory that holds per-run edge-bench output folders.",
    )
    parser.add_argument(
        "--run-id",
        help="Explicit edge-bench run id. A UTC timestamped id is generated if omitted.",
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

    from reposcan_contracts.config.loader import load_benchmark_manifest, load_deployment_config
    from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
    from reposcan_inference import (
        InferenceService,
        default_edge_run_id,
        run_edge_bench,
        write_edge_bench_artifacts,
    )

    args = parse_args()
    model_config_path = _resolve_path(repo_root, args.model_config)
    pipeline_config_path = _resolve_path(repo_root, args.pipeline_config)
    deployment_config_path = _resolve_path(repo_root, args.deployment_config)
    benchmark_manifest_path = _resolve_path(repo_root, args.benchmark_manifest)
    output_root = _resolve_path(repo_root, args.output_root)

    inference_service = InferenceService.from_config_paths(
        model_config_path=model_config_path,
        pipeline_config_path=pipeline_config_path,
    )
    deployment = load_deployment_config(deployment_config_path) if deployment_config_path is not None else None
    manifest = load_benchmark_manifest(benchmark_manifest_path)

    camera_profile = CameraProfile(camera_id=manifest.camera_id, source_type=SourceType.file)
    frames: list = []
    for index, expectation in enumerate(manifest.frames):
        frame_path = str(expectation.frame_path)
        frames.append(
            FrameEnvelope.model_validate(
                {
                    "frame_id": f"edge_bench_{index:06d}",
                    "camera_id": manifest.camera_id,
                    "timestamp_utc": "2026-04-15T00:00:00Z",
                    "frame_path": frame_path,
                    "frame_number": index,
                    "source_type": "file",
                    "camera_profile": camera_profile.model_dump(mode="json"),
                }
            )
        )

    run_id = args.run_id or default_edge_run_id()
    report = run_edge_bench(
        inference_service,
        frames,
        run_id=run_id,
        deployment=deployment,
    )
    assert output_root is not None
    run_dir = write_edge_bench_artifacts(report, output_root=output_root)

    run_manifest = {
        "run_id": run_id,
        "generated_at_utc": report.generated_at_utc,
        "git_head": _git_head(repo_root),
        "model_config": str(model_config_path) if model_config_path else None,
        "pipeline_config": str(pipeline_config_path) if pipeline_config_path else None,
        "deployment_config": str(deployment_config_path) if deployment_config_path else None,
        "benchmark_manifest": str(benchmark_manifest_path) if benchmark_manifest_path else None,
        "model_stack_name": report.model_stack_name,
        "frames_processed": report.frames_processed,
        "cold_start_latency_ms": report.cold_start_latency_ms,
        "peak_rss_mb": report.peak_rss_mb,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Edge bench run: {run_id}")
        print(f"Output: {run_dir}")
        print(f"Model stack: {report.model_stack_name}")
        print(f"Frames processed: {report.frames_processed}")
        print(f"Cold start latency: {report.cold_start_latency_ms:.2f} ms")
        print(
            "End-to-end: "
            f"avg={report.end_to_end.average_ms:.2f}ms "
            f"p50={report.end_to_end.p50_ms:.2f}ms "
            f"p95={report.end_to_end.p95_ms:.2f}ms "
            f"p99={report.end_to_end.p99_ms:.2f}ms"
        )
        for stage in report.stages:
            if stage.count == 0:
                continue
            print(
                f"- {stage.stage}: "
                f"avg={stage.average_ms:.2f}ms "
                f"p95={stage.p95_ms:.2f}ms "
                f"max={stage.max_ms:.2f}ms"
            )
        if report.peak_rss_mb is not None:
            print(f"Peak RSS: {report.peak_rss_mb:.1f} MB ({report.peak_rss_source})")
        else:
            print("Peak RSS: unavailable on this host")
        if report.recommendations:
            print("Recommendations:")
            for rec in report.recommendations:
                print(f"- {rec}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
