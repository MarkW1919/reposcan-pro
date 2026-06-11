from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from reposcan_api import create_app
from reposcan_capture import CaptureService, FileSequenceFrameSource
from reposcan_contracts.config.camera import CameraConfig
from reposcan_contracts.config.loader import load_model_config, load_pipeline_config
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, PreparedFrame, SourceType
from reposcan_contracts.inference import AttributePredictions, PlateDetection, VehicleDetection
from reposcan_contracts.detection import PlateCandidate
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_inference import (
    FrameToCandidateWorkflow,
    HeadlessFileSequenceRunner,
    InferenceService,
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from reposcan_preprocessing import PreprocessingService
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService


def _write_demo_image(path, *, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (96, 64), color=color)
    image.save(path, format="JPEG")


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


def test_preprocessing_service_generates_prepared_artifact_for_real_image(tmp_path):
    source_path = tmp_path / "frame_0001.jpg"
    _write_demo_image(source_path, color=(12, 12, 12))

    frame = FrameEnvelope.model_validate(
        {
            "frame_id": "frm_real_001",
            "camera_id": "cam_real_01",
            "timestamp_utc": "2026-03-20T12:00:00Z",
            "frame_path": str(source_path),
            "frame_number": 0,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_real_01",
                source_type=SourceType.file,
                ir_mode=True,
            ).model_dump(mode="json"),
        }
    )

    pipeline_config = load_pipeline_config("configs/pipelines/default-edge.yaml")
    prepared = PreprocessingService(
        pipeline_config,
        artifact_root=tmp_path / "preprocessed",
    ).prepare(frame)

    assert isinstance(prepared, PreparedFrame)
    assert prepared.raw_frame_path == str(source_path)
    assert prepared.prepared_frame_path != prepared.raw_frame_path
    assert (tmp_path / "preprocessed").exists()
    assert prepared.preprocessing.artifact_generated is True
    assert prepared.preprocessing.enhancement_backend in {"opencv", "pillow"}
    assert prepared.preprocessing.exposure_adjusted is True
    assert prepared.preprocessing.night_mode_triggered is True
    assert prepared.preprocessing.mean_brightness_after >= prepared.preprocessing.mean_brightness_before


def test_preprocessing_service_rectifies_plate_crop(tmp_path):
    source_path = tmp_path / "plate_crop.jpg"
    _write_demo_image(source_path, color=(20, 20, 20))

    pipeline_config = load_pipeline_config("configs/pipelines/default-edge.yaml")
    service = PreprocessingService(
        pipeline_config,
        artifact_root=tmp_path / "preprocessed",
    )

    rectified = service.prepare_plate_crop(
        source_path,
        corners=((6.0, 4.0), (90.0, 2.0), (92.0, 28.0), (4.0, 30.0)),
        output_size=(144, 48),
    )

    assert rectified.size == (144, 48)


def test_headless_file_sequence_runner_persists_fresh_detections_and_alerts(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for name in ("frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg"):
        (frames_dir / name).write_bytes(b"frame-bytes")

    storage_service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    storage_service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_demo_001",
                "plate_text": "6BZN220",
                "label": "Demo tow-ready",
                "created_at_utc": "2026-03-20T11:00:00Z",
                "updated_at_utc": "2026-03-20T11:00:00Z",
            }
        )
    )

    runner = HeadlessFileSequenceRunner.from_config_paths(storage_service=storage_service)
    summary = runner.run_file_sequence(
        frames_dir,
        start_timestamp_utc="2026-03-20T12:00:00Z",
        frame_interval_ms=100.0,
        sequence_id="seq_runtime_demo",
    )

    assert summary.frames_captured == 3
    assert summary.candidates_processed == 3
    assert summary.tracks_finalized == 1
    assert len(summary.stored_detection_ids) == 1
    assert len(summary.created_alert_ids) == 1

    client = TestClient(create_app(storage_service=storage_service))
    overview = client.get("/dashboard/overview").json()
    assert summary.stored_detection_ids[0] in {record["detection_id"] for record in overview["detections"]}
    assert summary.created_alert_ids[0] in {record["alert_id"] for record in overview["alerts"]}


def test_headless_runner_writes_preprocessed_artifacts_and_preserves_raw_evidence(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for index, color in enumerate(((10, 10, 10), (14, 14, 14), (18, 18, 18)), start=1):
        _write_demo_image(frames_dir / f"frame_{index:04d}.jpg", color=color)

    storage_service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    storage_service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_demo_002",
                "plate_text": "6BZN220",
                "label": "Night recovery target",
                "created_at_utc": "2026-03-20T11:00:00Z",
                "updated_at_utc": "2026-03-20T11:00:00Z",
            }
        )
    )

    runner = HeadlessFileSequenceRunner.from_config_paths(
        storage_service=storage_service,
        preprocessed_root=tmp_path / "preprocessed",
    )
    summary = runner.run_file_sequence(
        frames_dir,
        start_timestamp_utc="2026-03-20T12:00:00Z",
        frame_interval_ms=100.0,
        sequence_id="seq_runtime_real_images",
    )

    prepared_files = sorted((tmp_path / "preprocessed").rglob("*_prepared.jpg"))
    detection = storage_service.get_detection(summary.stored_detection_ids[0])

    assert len(prepared_files) == 3
    assert detection is not None
    assert detection.image_path.startswith(str(frames_dir))
    assert not detection.image_path.startswith(str(tmp_path / "preprocessed"))


def test_headless_file_sequence_runner_requires_enough_frames(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "frame_0001.jpg").write_bytes(b"frame-bytes")

    runner = HeadlessFileSequenceRunner.from_config_paths(
        storage_service=StorageService(
            repository=InMemoryStorageRepository(),
            media_root=tmp_path / "media",
        )
    )

    with pytest.raises(ValueError, match="At least 3 frames are required"):
        runner.run_file_sequence(
            frames_dir,
            start_timestamp_utc="2026-03-20T12:00:00Z",
            frame_interval_ms=100.0,
            sequence_id="seq_too_short",
        )
