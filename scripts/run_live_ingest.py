from __future__ import annotations

import argparse
import signal
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
    parser = argparse.ArgumentParser(description="Run live RepoScan capture -> inference -> storage ingest.")
    parser.add_argument("--camera-config-dir", default="configs/cameras")
    parser.add_argument("--camera-pattern", default="*.yaml")
    parser.add_argument("--model-config", default="configs/models/local-onnx-runtime.yaml")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--deployment-config", default="configs/deployments/local-dev.yaml")
    parser.add_argument("--metadata-root", default="runtime/storage")
    parser.add_argument("--preprocessed-root", default="runtime/preprocessed")
    parser.add_argument("--capture-output-root", default="media/live-capture")
    parser.add_argument("--max-frames-per-camera", type=int)
    return parser.parse_args()


def _resolve(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_alerting import AlertingService
    from reposcan_capture import CameraRegistry, CaptureService, LiveFrameSource
    from reposcan_contracts.config.camera import SourceType
    from reposcan_contracts.config.loader import load_model_config, load_pipeline_config
    from reposcan_inference import InferenceService
    from reposcan_inference.adapter_factory import build_runtime_adapter_bundle
    from reposcan_inference.workflow import FrameToCandidateWorkflow
    from reposcan_preprocessing import PreprocessingService
    from reposcan_storage.service import create_development_storage_service
    from reposcan_tracking import TrackingService

    args = parse_args()
    stop_requested = False

    def _request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    camera_registry = CameraRegistry.from_directory(
        _resolve(repo_root, args.camera_config_dir),
        pattern=args.camera_pattern,
    )
    cameras = [
        camera
        for camera in camera_registry.list_cameras(enabled_only=True)
        if camera.source_type in {SourceType.rtsp, SourceType.usb}
    ]
    if not cameras:
        print("No enabled RTSP or USB cameras found for live ingest.", file=sys.stderr)
        return 1

    model_stack = load_model_config(_resolve(repo_root, args.model_config))
    pipeline_config = load_pipeline_config(_resolve(repo_root, args.pipeline_config))
    adapters = build_runtime_adapter_bundle(model_stack)
    inference_service = InferenceService.from_config_paths(
        model_config_path=_resolve(repo_root, args.model_config),
        pipeline_config_path=_resolve(repo_root, args.pipeline_config),
        adapters=adapters,
    )
    workflow = FrameToCandidateWorkflow(
        inference_service=inference_service,
        preprocessing_service=PreprocessingService(
            pipeline_config,
            artifact_root=_resolve(repo_root, args.preprocessed_root),
        ),
    )
    tracking_service = TrackingService.from_config_path(str(_resolve(repo_root, args.pipeline_config)))
    alerting_service = AlertingService.from_config_path(str(_resolve(repo_root, args.pipeline_config)))
    storage_service = create_development_storage_service(
        deployment_config_path=_resolve(repo_root, args.deployment_config),
        metadata_root=_resolve(repo_root, args.metadata_root),
    )
    capture_service = CaptureService()

    print(f"Starting live ingest for {len(cameras)} camera(s).")
    processed_frames = 0
    for camera in cameras:
        if stop_requested:
            break
        source = LiveFrameSource(
            camera,
            output_root=_resolve(repo_root, args.capture_output_root),
            sequence_id=f"live_{camera.camera_id}",
            max_frames=args.max_frames_per_camera,
        )
        for captured_frame in source:
            if stop_requested:
                break
            frame = capture_service.capture_frame(camera, captured_frame)
            candidate = workflow.process(frame)
            finalized_tracks = tracking_service.ingest(frame, candidate)
            active_hotlists = storage_service.list_hotlists(active_only=True, limit=500)
            for track in finalized_tracks:
                storage_service.store_tracked_detection(track)
                alert = alerting_service.evaluate(track, active_hotlists)
                if alert is not None:
                    storage_service.store_alert(alert)
            processed_frames += 1

    for camera in cameras:
        finalized_tracks = tracking_service.flush(camera_id=camera.camera_id)
        active_hotlists = storage_service.list_hotlists(active_only=True, limit=500)
        for track in finalized_tracks:
            storage_service.store_tracked_detection(track)
            alert = alerting_service.evaluate(track, active_hotlists)
            if alert is not None:
                storage_service.store_alert(alert)

    print(f"Live ingest stopped. Frames processed: {processed_frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
