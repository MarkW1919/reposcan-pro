from __future__ import annotations

import pytest

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.dispatch import DispatchAssignmentRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorSessionRecord
from reposcan_contracts.review import ReviewRecord
from reposcan_contracts.tracking import TrackedDetection
from reposcan_storage.json_store import JsonFileStorageRepository
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import (
    AlertNotFoundError,
    AssignmentNotFoundError,
    DetectionNotFoundError,
    FollowUpNotFoundError,
    StorageService,
)
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


def _follow_up_record() -> FollowUpRecord:
    return FollowUpRecord.model_validate(
        {
            "follow_up_id": "fu_001",
            "detection_id": "det_20260320_000001",
            "alert_id": "alert_001",
            "plate_text": "8ABC123",
            "priority": "critical",
            "status": "open",
            "created_by_operator_id": "cab_demo_01",
            "assigned_operator_id": "tow_lead_02",
            "summary": "Pin this target for the field team.",
            "created_at_utc": "2026-03-20T04:18:00Z",
            "updated_at_utc": "2026-03-20T04:18:00Z",
        }
    )


def _assignment_record() -> DispatchAssignmentRecord:
    return DispatchAssignmentRecord.model_validate(
        {
            "assignment_id": "asg_001",
            "detection_id": "det_20260320_000001",
            "alert_id": "alert_001",
            "plate_text": "8ABC123",
            "priority": "critical",
            "status": "assigned",
            "created_by_operator_id": "cab_demo_01",
            "assigned_operator_id": "tow_lead_02",
            "assigned_unit_label": "Truck 4",
            "destination_label": "Shoreline Marina south lot",
            "summary": "Tow crew staged for pickup.",
            "created_at_utc": "2026-03-20T04:19:00Z",
            "updated_at_utc": "2026-03-20T04:19:00Z",
        }
    )


def _session_record() -> OperatorSessionRecord:
    return OperatorSessionRecord.model_validate(
        {
            "session_id": "session_001",
            "principal_id": "operator_demo",
            "display_name": "Operator Demo",
            "authenticated": True,
            "roles": ["viewer", "operator"],
            "client_label": "cab_console_01",
            "workspace": "dashboard",
            "selected_detection_id": "det_20260320_000001",
            "last_seen_at_utc": "2026-03-20T04:20:00Z",
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
    follow_up = _follow_up_record()
    assignment = _assignment_record()
    review = _review_record()
    hotlist = _hotlist_entry()
    alert = _alert_record()
    session = _session_record()

    repository.upsert_detection(detection)
    repository.upsert_follow_up(follow_up)
    repository.upsert_assignment(assignment)
    repository.create_review(review)
    repository.upsert_hotlist(hotlist)
    repository.create_alert(alert)
    repository.upsert_operator_session(session)

    assert repository.get_detection(detection.detection_id) == detection
    assert repository.get_follow_up(follow_up.follow_up_id) == follow_up
    assert repository.get_assignment(assignment.assignment_id) == assignment
    assert repository.list_reviews(detection.detection_id) == [review]
    assert repository.get_hotlist(hotlist.entry_id) == hotlist
    assert repository.get_alert(alert.alert_id) == alert
    assert repository.list_operator_sessions() == [session]

    assert repository.delete_hotlist(hotlist.entry_id) is True
    assert repository.get_hotlist(hotlist.entry_id) is None


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


def test_storage_service_updates_alert_state(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    service.store_alert(_alert_record())

    updated = service.update_alert(
        _alert_record().model_copy(
            update={
                "status": "acknowledged",
                "response_operator_id": "cab_demo_01",
                "response_notes": "Operator marked the vehicle as on scene.",
                "updated_at_utc": "2026-03-20T04:21:00Z",
            }
        )
    )

    assert updated.status == "acknowledged"
    assert updated.response_operator_id == "cab_demo_01"
    assert updated.response_notes == "Operator marked the vehicle as on scene."
    assert updated.updated_at_utc == "2026-03-20T04:21:00Z"
    assert service.get_alert(updated.alert_id) == updated


def test_storage_service_creates_and_updates_follow_up_and_assignment(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    service.store_detection(_detection_record())
    service.store_alert(_alert_record())

    created_follow_up = service.create_follow_up(_follow_up_record())
    created_assignment = service.create_assignment(_assignment_record())

    updated_follow_up = service.update_follow_up(
        created_follow_up.model_copy(
            update={
                "status": "monitoring",
                "updated_at_utc": "2026-03-20T04:19:00Z",
            }
        )
    )
    updated_assignment = service.update_assignment(
        created_assignment.model_copy(
            update={
                "status": "en_route",
                "updated_at_utc": "2026-03-20T04:20:00Z",
            }
        )
    )

    assert updated_follow_up.status == "monitoring"
    assert updated_assignment.status == "en_route"
    assert service.list_follow_ups(limit=10)[0].follow_up_id == created_follow_up.follow_up_id
    assert service.list_assignments(limit=10)[0].assignment_id == created_assignment.assignment_id


def test_storage_service_rejects_missing_follow_up_and_assignment_updates(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    service.store_detection(_detection_record())

    with pytest.raises(FollowUpNotFoundError):
        service.update_follow_up(_follow_up_record())

    with pytest.raises(AssignmentNotFoundError):
        service.update_assignment(_assignment_record())


def test_storage_service_tracks_active_operator_sessions(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    active = service.touch_operator_session(_session_record())
    stale = service.touch_operator_session(
        _session_record().model_copy(
            update={
                "session_id": "session_stale",
                "last_seen_at_utc": "2026-03-20T04:00:00Z",
            }
        )
    )

    assert active.session_id == "session_001"
    assert stale.session_id == "session_stale"
    sessions = service.list_operator_sessions(limit=10, max_age_seconds=1_000_000)
    assert {session.session_id for session in sessions} == {"session_001", "session_stale"}


def test_storage_service_rejects_update_for_missing_alert(tmp_path):
    service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )

    with pytest.raises(AlertNotFoundError):
        service.update_alert(_alert_record())


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
