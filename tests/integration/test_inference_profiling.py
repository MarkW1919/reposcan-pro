from __future__ import annotations

from reposcan_contracts.config.loader import load_deployment_config, load_model_config, load_pipeline_config
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.inference import PlateDetection, VehicleDetection
from reposcan_contracts.detection import PlateCandidate
from reposcan_inference import (
    InferenceProfiler,
    InferenceService,
    ModelAdapterBundle,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)


def _frame(frame_number: int) -> FrameEnvelope:
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"frm_profile_{frame_number}",
            "camera_id": "cam_profile_01",
            "timestamp_utc": f"2026-03-20T18:00:0{frame_number}Z",
            "frame_path": f"media/frames/cam_profile_01/frame_{frame_number:06d}.jpg",
            "frame_number": frame_number,
            "source_type": "file",
            "camera_profile": CameraProfile(camera_id="cam_profile_01", source_type=SourceType.file).model_dump(mode="json"),
        }
    )


def test_inference_profiler_returns_latency_profile():
    model_stack = load_model_config("configs/models/example-model-stack.yaml")
    pipeline = load_pipeline_config("configs/pipelines/default-edge.yaml")
    deployment = load_deployment_config("configs/deployments/jetson-orin-edge.yaml")
    service = InferenceService(
        model_stack,
        pipeline,
        ModelAdapterBundle(
            vehicle_detector=StaticVehicleDetectorAdapter(
                model_stack.vehicle_detector,
                outputs=[VehicleDetection.model_validate({"bbox": {"x": 1, "y": 2, "w": 30, "h": 40}, "confidence": 0.9, "class_label": "car"})],
            ),
            plate_detector=StaticPlateDetectorAdapter(
                model_stack.plate_detector,
                outputs=[PlateDetection.model_validate({"bbox": {"x": 3, "y": 4, "w": 10, "h": 8}, "confidence": 0.88, "vehicle_index": 0})],
            ),
            ocr=StaticOcrAdapter(
                model_stack.ocr,
                outputs=[PlateCandidate.model_validate({"text": "8ABC123", "confidence": 0.93})],
            ),
            classifier=None,
        ),
    )

    profile = InferenceProfiler(service).benchmark([_frame(1), _frame(2)], deployment=deployment)

    assert profile.frames_processed == 2
    assert profile.average_latency_ms >= 0.0
    assert profile.max_latency_ms >= profile.average_latency_ms
    assert profile.average_vehicles_per_frame == 1
    assert any("TensorRT" in recommendation for recommendation in profile.recommendations)
