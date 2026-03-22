from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "preprocessing" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark RepoScan Pro preprocessing over a folder of local frames."
    )
    parser.add_argument("--frames-dir", required=True, help="Directory containing input frames")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--artifact-root", default="runtime/preprocessed-benchmark")
    parser.add_argument("--glob-pattern", default="*.jpg")
    parser.add_argument("--camera-id", default="cam_preprocess_benchmark_01")
    parser.add_argument("--sequence-id", default="seq_preprocess_benchmark")
    parser.add_argument("--start-timestamp-utc", default="2026-03-22T12:00:00Z")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
    from reposcan_preprocessing import PreprocessingService

    args = parse_args()
    frames_dir = repo_root / args.frames_dir
    frame_paths = sorted(path for path in frames_dir.glob(args.glob_pattern) if path.is_file())
    if not frame_paths:
        print(f"No frame files matched '{args.glob_pattern}' in '{frames_dir}'", file=sys.stderr)
        return 1

    service = PreprocessingService.from_config_path(
        str(repo_root / args.pipeline_config),
        artifact_root=repo_root / args.artifact_root,
    )
    profile = CameraProfile(camera_id=args.camera_id, source_type=SourceType.file, ir_mode=True)

    prepared_frames = []
    for index, frame_path in enumerate(frame_paths):
        frame = FrameEnvelope.model_validate(
            {
                "frame_id": f"frm_benchmark_{index:04d}",
                "camera_id": args.camera_id,
                "timestamp_utc": args.start_timestamp_utc,
                "frame_path": str(frame_path),
                "frame_number": index,
                "source_type": "file",
                "sequence_id": args.sequence_id,
                "camera_profile": profile.model_dump(mode="json"),
            }
        )
        prepared_frames.append(service.prepare(frame))

    metadata = [prepared.preprocessing for prepared in prepared_frames]
    brightness_before = [item.mean_brightness_before for item in metadata if item.mean_brightness_before is not None]
    brightness_after = [item.mean_brightness_after for item in metadata if item.mean_brightness_after is not None]
    exposure_adjusted = sum(1 for item in metadata if item.exposure_adjusted)
    clahe_applied = sum(1 for item in metadata if item.clahe_applied)

    avg_before = sum(brightness_before) / len(brightness_before) if brightness_before else 0.0
    avg_after = sum(brightness_after) / len(brightness_after) if brightness_after else 0.0

    print("RepoScan Pro preprocessing benchmark complete.")
    print(f"Frames processed: {len(prepared_frames)}")
    print(f"Artifacts generated: {sum(1 for item in metadata if item.artifact_generated)}")
    print(f"Exposure adjusted: {exposure_adjusted}")
    print(f"CLAHE applied: {clahe_applied}")
    print(f"Average brightness before: {avg_before:.2f}")
    print(f"Average brightness after: {avg_after:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
