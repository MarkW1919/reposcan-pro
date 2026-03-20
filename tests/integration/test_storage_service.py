from __future__ import annotations

import pytest

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord
from reposcan_contracts.tracking import TrackedDetection
from reposcan_storage.json_store import JsonFileStorageRepository
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import DetectionNotFoundError, StorageService
from reposcan_storage.dev_seed import seed_development_operator_data


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


def _newer_review_record() -> ReviewRecord:
    return ReviewRecord.model_validate(
        {
            "review_id": "rev_002",
            "detection_id": "det_20260320_000001",
            "action": "flag",
            "reviewed_at_utc": "2026-03-20T04:16:00Z",
        }
    )


def _hotlist_entry() -> HotlistEntry:
    return HotlistEntry.model_validate(
        {
            "entry_id": "hl_001",
            "plate_text": "8ABC123",
            "label": "Case 42",
            "created_at_utc": "2026-03-20T04:00:00Z",
            "updated_at_utc": "2026-03-20T04:00:00Z",
        }
    )


def _alert_record() -> AlertRecord:
    return AlertRecord.model_validate(
        {
            "alert_id": "alert_001",
            "detection_id": "det_20260320_000001",
            "hotlist_entry_id": "hl_001",
            "timestamp_utc": "2026-03-20T04:20:00Z",
            "camera_id": "cam_north_gate_01",
            "matched_plate_text": "8ABC123",
            "match_confidence": 0.92,
            "match_type": "exact",
            "hotlist_label": "Case 42",
        }
    )


def _tracked_detection() -> TrackedDetection:
    return TrackedDetection.model_validate(
        {
            "detection_id": "det_tracked_001",
            "tracker_id": "trk_001",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": "2026-03-20T04:10:00Z",
            "best_plate_candidate": {"text": "8ABC123", "confidence": 0.93},
            "alternate_plate_candidates": [{"text": "8A8C123", "confidence": 0.41}],
            "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
            "plate_bbox": {"x": 518, "y": 338, "w": 86, "h": 28},
            "vehicle_attributes": {
                "color": "white",
                "color_confidence": 0.88,
                "make": "toyota",
                "make_confidence": 0.67,
                "model": "camry",
                "model_confidence": 0.54,
            },
            "evidence_refs": {"best_frame_path": "media/frames/cam_north_gate_01/frame_000542.jpg"},
            "confidence_summary": {
                "best_plate_confidence": 0.93,
                "ocr_candidate_count": 3,
                "frames_tracked": 3,
                "first_seen_utc": "2026-03-20T04:09:00Z",
                "last_seen_utc": "2026-03-20T04:10:00Z",
            },
            "frame_number": 542,
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
    hotlist = _hotlist_entry()
    alert = _alert_record()

    repository.upsert_detection(detection)
    repository.create_review(review)
    repository.upsert_hotlist(hotlist)
    repository.create_alert(alert)

    assert repository.get_detection(detection.detection_id) == detection
    assert repository.list_reviews(detection.detection_id) == [review]
    assert repository.get_hotlist(hotlist.entry_id) == hotlist
    assert repository.get_alert(alert.alert_id) == alert


def test_review_history_is_returned_newest_first(tmp_path):
    repository = JsonFileStorageRepository(tmp_path / "metadata")
    detection = _detection_record()

    repository.upsert_detection(detection)
    repository.create_review(_review_record())
    repository.create_review(_newer_review_record())

    reviews = repository.list_reviews(detection.detection_id)

    assert [review.review_id for review in reviews] == ["rev_002", "rev_001"]


def test_storage_service_rejects_review_for_missing_detection(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    with pytest.raises(DetectionNotFoundError):
        service.create_review(_review_record())


def test_storage_service_stores_tracked_detection(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    detection = service.store_tracked_detection(_tracked_detection())

    assert detection.plate_text == "8ABC123"
    assert detection.vehicle_model == "camry"
    assert service.get_detection(detection.detection_id) == detection


def test_seed_development_operator_data_populates_fresh_store(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    seed_development_operator_data(service)

    assert len(service.list_detections(limit=10)) >= 3
    assert len(service.list_alerts(limit=10)) >= 2
    assert len(service.list_hotlists(limit=10)) >= 2
    assert len(service.list_reviews("det_20260320_010001")) >= 1


def test_seed_development_operator_data_is_idempotent(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    seed_development_operator_data(service)
    first_detection_ids = [record.detection_id for record in service.list_detections(limit=10)]
    seed_development_operator_data(service)
    second_detection_ids = [record.detection_id for record in service.list_detections(limit=10)]

    assert second_detection_ids == first_detection_ids
