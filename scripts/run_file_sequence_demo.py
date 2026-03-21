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
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a headless file-sequence ingest simulation and write fresh detections into local storage."
    )
    parser.add_argument("--frames-dir", required=True, help="Directory containing input frame files")
    parser.add_argument("--camera-config", default="configs/cameras/local-file-demo.yaml")
    parser.add_argument("--model-config", default="configs/models/example-model-stack.yaml")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--deployment-config", default="configs/deployments/local-dev.yaml")
    parser.add_argument("--metadata-root", default="runtime/storage")
    parser.add_argument("--preprocessed-root", default="runtime/preprocessed")
    parser.add_argument("--start-timestamp-utc", default="2026-03-20T12:00:00Z")
    parser.add_argument("--frame-interval-ms", type=float, default=100.0)
    parser.add_argument("--glob-pattern", default="*.jpg")
    parser.add_argument("--sequence-id", default="seq_file_demo")
    parser.add_argument("--plate-text", default="6BZN220")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_inference.runtime import HeadlessFileSequenceRunner

    args = parse_args()
    runner = HeadlessFileSequenceRunner.from_config_paths(
        camera_config_path=repo_root / args.camera_config,
        model_config_path=repo_root / args.model_config,
        pipeline_config_path=repo_root / args.pipeline_config,
        deployment_config_path=repo_root / args.deployment_config,
        metadata_root=repo_root / args.metadata_root,
        preprocessed_root=repo_root / args.preprocessed_root,
        plate_text=args.plate_text,
    )
    summary = runner.run_file_sequence(
        repo_root / args.frames_dir,
        start_timestamp_utc=args.start_timestamp_utc,
        frame_interval_ms=args.frame_interval_ms,
        glob_pattern=args.glob_pattern,
        sequence_id=args.sequence_id,
    )

    print("RepoScan Pro file-sequence ingest complete.")
    print(f"Frames captured: {summary.frames_captured}")
    print(f"Candidates processed: {summary.candidates_processed}")
    print(f"Tracks finalized: {summary.tracks_finalized}")
    print(f"Stored detections: {', '.join(summary.stored_detection_ids) or 'none'}")
    print(f"Created alerts: {', '.join(summary.created_alert_ids) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
