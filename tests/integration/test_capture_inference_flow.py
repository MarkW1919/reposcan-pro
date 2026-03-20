from __future__ import annotations

from reposcan_capture import CaptureService, FileSequenceFrameSource
from reposcan_contracts.config.camera import CameraConfig
from reposcan_contracts.config.loader import load_model_config, load_pipeline_config
from reposcan_contracts.inference import AttributePredictions, PlateDetection, VehicleDetection
from reposcan_contracts.detection import PlateCandidate
from reposcan_inference import (
    FrameToCandidateWorkflow,
    InferenceService,
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from reposcan_preprocessing import PreprocessingService


def test_capture_to_inference_workflow_with_file_source(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for name in ("frame_0001.jpg", "frame_0002.jpg"):
        (frames_dir / name).write_bytes(b"not-a-real-image-but-good-enough-for-skeleton-tests")

    camera = CameraConfig.model_validate(
        {
            "camera_id": "cam_file_test_01",
            "display_name": "File Test Camera",
            "source_type": "file",
            "stream_url": str(frames_dir),
            "sensor": {
                "type": "test_sensor",
                "resolution_w": 1920,
                "resolution_h": 1080,
                "fps": 10.0,
            },
            "mounting": {
                "gps_latitude": 34.1,
                "gps_longitude": -118.2,
                "gps_accuracy_m": 2.0,
            },
        }
    )

    capture_service = CaptureService()
    source = FileSequenceFrameSource.from_directory(
        frames_dir,
        start_timestamp_utc="2026-03-20T12:00:00Z",
        frame_interval_ms=100.0,
        sequence_id="seq_phase3",
    )
    envelopes = capture_service.capture_sequence(camera, source)

    model_stack = load_model_config("configs/models/example-model-stack.yaml")
    pipeline_config = load_pipeline_config("configs/pipelines/default-edge.yaml")
    adapters = ModelAdapterBundle(
        vehicle_detector=StaticVehicleDetectorAdapter(
            model_stack.vehicle_detector,
            outputs=[
                VehicleDetection.model_validate(
                    {
                        "bbox": {"x": 200, "y": 100, "w": 400, "h": 220},
                        "confidence": 0.91,
                        "class_label": "car",
                    }
                )
            ],
        ),
        plate_detector=StaticPlateDetectorAdapter(
            model_stack.plate_detector,
            outputs=[
                PlateDetection.model_validate(
                    {
                        "bbox": {"x": 310, "y": 240, "w": 120, "h": 40},
                        "confidence": 0.88,
                        "vehicle_index": 0,
                    }
                )
            ],
        ),
        ocr=StaticOcrAdapter(
            model_stack.ocr,
            outputs=[PlateCandidate.model_validate({"text": "8ABC123", "confidence": 0.93})],
        ),
        classifier=StaticClassifierAdapter(
            model_stack.classifier,
            outputs=[
                AttributePredictions.model_validate(
                    {
                        "color": "white",
                        "color_confidence": 0.87,
                        "make": "toyota",
                        "make_confidence": 0.68,
                        "model": "camry",
                        "model_confidence": 0.55,
                    }
                )
            ],
        ),
    )
    inference_service = InferenceService(model_stack, pipeline_config, adapters)
    workflow = FrameToCandidateWorkflow(
        inference_service=inference_service,
        preprocessing_service=PreprocessingService(pipeline_config),
    )

    candidates = workflow.process_many(envelopes)

    assert len(candidates) == 2
    first = candidates[0]
    assert first.camera_id == "cam_file_test_01"
    assert first.vehicle_detections[0].class_label == "car"
    assert first.plate_detections[0].vehicle_index == 0
    assert first.ocr_candidates[0].text == "8ABC123"
    assert first.attribute_predictions[0].model_label == "camry"
    assert first.model_versions.vehicle_detector.startswith("yolov8n-vehicle|onnx|")
    assert envelopes[0].camera_profile.sensor_type == "test_sensor"
    assert envelopes[0].gps_snapshot.latitude == 34.1
    assert envelopes[1].frame_number == 1
