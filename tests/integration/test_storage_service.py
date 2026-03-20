from __future__ import annotations

from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.review import ReviewRecord
from reposcan_storage.json_store import JsonFileStorageRepository
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import DetectionNotFoundError, StorageService


def _detection_record() -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": "det_20260320_000001",
            "timestamp_utc": "2026-03-20T04:10:00Z",
            "camera_id": "cam_north_gate_01",
            "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
            "image_path": "media/frames/cam_north_gate_01/frame_000542.jpg",
            "frame_number": 542,
        }
    )


def _review_record() -> ReviewRecord:
    return ReviewRecord.model_validate(
        {
            "review_id": "rev_001",
            "detection_id": "det_20260320_000001",
            "action": "confirm",
            "reviewed_at_utc": "2026-03-20T04:15:00Z",
        }
    )


def test_storage_service_ensures_media_layout(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    assert service.media_layout.frames.exists()
    assert service.media_layout.crops.exists()
    assert service.media_layout.snippets.exists()
    assert service.media_layout.exports.exists()


def test_json_repository_roundtrip(tmp_path):
    repository = JsonFileStorageRepository(tmp_path / "metadata")
    detection = _detection_record()
    review = _review_record()

    repository.upsert_detection(detection)
    repository.create_review(review)

    assert repository.get_detection(detection.detection_id) == detection
    assert repository.list_reviews(detection.detection_id) == [review]


def test_storage_service_rejects_review_for_missing_detection(tmp_path):
    import pytest

    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    with pytest.raises(DetectionNotFoundError):
        service.create_review(_review_record())
