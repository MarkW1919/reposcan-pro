from __future__ import annotations

import json

from PIL import Image

from reposcan_contracts.hotlist import HotlistEntry
from reposcan_inference import HeadlessFileSequenceRunner, validate_model_stack
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService
from reposcan_contracts.config.loader import load_model_config


def _write_demo_image(path, *, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (128, 72), color=color)
    image.save(path, format="JPEG")


def test_local_demo_model_stack_validates_ready():
    model_stack = load_model_config("configs/models/local-demo-runtime.yaml")

    report = validate_model_stack(model_stack)

    assert report.ready is True
    assert report.error_count == 0
    assert all(stage.ready for stage in report.stages)


def test_example_model_stack_reports_missing_artifacts():
    model_stack = load_model_config("configs/models/example-model-stack.yaml")

    report = validate_model_stack(model_stack)

    assert report.ready is False
    assert report.error_count >= 3
    assert any("does not exist" in issue.message for stage in report.stages for issue in stage.issues)


def test_headless_runner_uses_runtime_sidecars(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()

    sidecar_payload = {
        "vehicle_detections": [
            {
                "bbox": {"x": 22, "y": 16, "w": 72, "h": 38},
                "confidence": 0.94,
                "class_label": "car",
            }
        ],
        "plate_detections": [
            {
                "bbox": {"x": 48, "y": 36, "w": 26, "h": 10},
                "confidence": 0.9,
                "vehicle_index": 0,
            }
        ],
        "ocr_candidates": [
            {
                "text": "7BLUE42",
                "confidence": 0.96,
            }
        ],
        "attribute_predictions": [
            {
                "color": "blue",
                "color_confidence": 0.92,
                "make": "honda",
                "make_confidence": 0.84,
                "model": "accord",
                "model_confidence": 0.79,
                "year": "2017-2020",
                "year_confidence": 0.68,
            }
        ],
    }

    for index in range(1, 4):
        frame_path = frames_dir / f"frame_{index:04d}.jpg"
        _write_demo_image(frame_path, color=(56, 92, 182))
        frame_path.with_suffix(".inference.json").write_text(json.dumps(sidecar_payload), encoding="utf-8")

    storage_service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    storage_service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_runtime_sidecar_01",
                "plate_text": "7BLUE42",
                "label": "Sidecar demo target",
                "created_at_utc": "2026-03-22T10:00:00Z",
                "updated_at_utc": "2026-03-22T10:00:00Z",
            }
        )
    )

    runner = HeadlessFileSequenceRunner.from_config_paths(
        model_config_path="configs/models/local-demo-runtime.yaml",
        storage_service=storage_service,
        preprocessed_root=tmp_path / "preprocessed",
    )
    summary = runner.run_file_sequence(
        frames_dir,
        start_timestamp_utc="2026-03-22T12:00:00Z",
        frame_interval_ms=100.0,
        sequence_id="seq_runtime_sidecar",
    )

    detection = storage_service.get_detection(summary.stored_detection_ids[0])

    assert summary.tracks_finalized == 1
    assert len(summary.created_alert_ids) == 1
    assert detection is not None
    assert detection.plate_text == "7BLUE42"
    assert detection.vehicle_color == "blue"
    assert detection.vehicle_make == "honda"
    assert detection.vehicle_model == "accord"
    assert detection.optional_vehicle_year == "2017-2020"
