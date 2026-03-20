from __future__ import annotations

from fastapi.testclient import TestClient

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_api import create_app
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService


def _seeded_client(tmp_path) -> tuple[TestClient, StorageService]:
    repository = InMemoryStorageRepository()
    service = StorageService(repository=repository, media_root=tmp_path / "media")
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_000001",
                "timestamp_utc": "2026-03-20T04:10:00Z",
                "camera_id": "cam_north_gate_01",
                "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
                "image_path": "media/frames/cam_north_gate_01/frame_000542.jpg",
                "frame_number": 542,
            }
        )
    )
    return TestClient(create_app(storage_service=service)), service


def test_health_endpoint_reports_api_and_storage(tmp_path):
    client, _ = _seeded_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "api"
    dependency_names = {item["name"] for item in payload["dependencies"]}
    assert "metadata-store" in dependency_names
    assert "media-root" in dependency_names


def test_list_detections_returns_seeded_records(tmp_path):
    client, _ = _seeded_client(tmp_path)

    response = client.get("/detections")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["detection_id"] == "det_20260320_000001"


def test_get_detection_by_id(tmp_path):
    client, _ = _seeded_client(tmp_path)

    response = client.get("/detections/det_20260320_000001")

    assert response.status_code == 200
    assert response.json()["camera_id"] == "cam_north_gate_01"


def test_missing_detection_returns_404(tmp_path):
    client, _ = _seeded_client(tmp_path)

    response = client.get("/detections/does-not-exist")

    assert response.status_code == 404


def test_post_review_persists_review(tmp_path):
    client, service = _seeded_client(tmp_path)

    response = client.post(
        "/reviews/det_20260320_000001",
        json={
            "action": "confirm",
            "reviewed_at_utc": "2026-03-20T04:15:00Z",
            "notes": "Operator confirmed the plate read.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["detection_id"] == "det_20260320_000001"
    assert payload["action"] == "confirm"
    assert len(service.list_reviews("det_20260320_000001")) == 1


def test_list_reviews_returns_review_history(tmp_path):
    client, _ = _seeded_client(tmp_path)
    client.post(
        "/reviews/det_20260320_000001",
        json={
            "action": "correct",
            "corrected_plate_text": "8XYZ999",
            "reviewed_at_utc": "2026-03-20T04:16:00Z",
        },
    )

    response = client.get("/reviews/det_20260320_000001")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["corrected_plate_text"] == "8XYZ999"


def test_post_review_missing_detection_returns_404(tmp_path):
    client, _ = _seeded_client(tmp_path)

    response = client.post(
        "/reviews/missing-id",
        json={
            "action": "confirm",
            "reviewed_at_utc": "2026-03-20T04:15:00Z",
        },
    )

    assert response.status_code == 404


def test_hotlist_crud_endpoints(tmp_path):
    client, _ = _seeded_client(tmp_path)

    create_response = client.post(
        "/hotlists",
        json={
            "plate_text": "8abc123",
            "label": "Case 42",
            "notes": "Monitor vehicle",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["plate_text"] == "8ABC123"

    list_response = client.get("/hotlists")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = client.put(
        f"/hotlists/{created['entry_id']}",
        json={
            "plate_text": "8ABC123",
            "label": "Case 42 Updated",
            "notes": "Escalated",
            "active": False,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Case 42 Updated"
    assert updated["active"] is False


def test_alert_endpoints_return_seeded_alerts(tmp_path):
    client, service = _seeded_client(tmp_path)
    alert = AlertRecord.model_validate(
        {
            "alert_id": "alert_001",
            "detection_id": "det_20260320_000001",
            "hotlist_entry_id": "hl_001",
            "timestamp_utc": "2026-03-20T04:20:00Z",
            "camera_id": "cam_north_gate_01",
            "matched_plate_text": "8ABC123",
            "match_confidence": 0.93,
            "match_type": "exact",
            "hotlist_label": "Case 42",
        }
    )
    hotlist = HotlistEntry.model_validate(
        {
            "entry_id": "hl_001",
            "plate_text": "8ABC123",
            "label": "Case 42",
            "created_at_utc": "2026-03-20T04:00:00Z",
            "updated_at_utc": "2026-03-20T04:00:00Z",
        }
    )
    service.create_hotlist(hotlist)
    service.store_alert(alert)

    list_response = client.get("/alerts")
    assert list_response.status_code == 200
    assert list_response.json()[0]["alert_id"] == "alert_001"

    detail_response = client.get("/alerts/alert_001")
    assert detail_response.status_code == 200
    assert detail_response.json()["hotlist_entry_id"] == "hl_001"


def test_dashboard_overview_returns_operator_summary(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_000002",
                "timestamp_utc": "2026-03-20T04:22:00Z",
                "camera_id": "cam_lot_east_03",
                "gps_latitude": 37.42061,
                "gps_longitude": -122.08155,
                "plate_text": "9XCA441",
                "plate_confidence": 0.86,
                "vehicle_bbox": {"x": 404, "y": 218, "w": 314, "h": 186},
                "image_path": "media/frames/cam_lot_east_03/frame_000644.jpg",
                "frame_number": 644,
                "vehicle_color": "gray",
                "vehicle_make": "honda",
                "vehicle_model": "accord",
                "optional_vehicle_year": "2017-2020",
            }
        )
    )
    hotlist = HotlistEntry.model_validate(
        {
            "entry_id": "hl_002",
            "plate_text": "6BZN220",
            "label": "Marina tow-ready",
            "created_at_utc": "2026-03-20T04:00:00Z",
            "updated_at_utc": "2026-03-20T04:00:00Z",
        }
    )
    alert = AlertRecord.model_validate(
        {
            "alert_id": "alert_002",
            "detection_id": "det_20260320_000001",
            "hotlist_entry_id": "hl_002",
            "timestamp_utc": "2026-03-20T04:21:00Z",
            "camera_id": "cam_north_gate_01",
            "matched_plate_text": "6BZN220",
            "match_confidence": 0.95,
            "match_type": "exact",
            "hotlist_label": "Marina tow-ready",
        }
    )
    service.create_hotlist(hotlist)
    service.store_alert(alert)

    response = client.get("/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["recent_detections"] == 2
    assert payload["counts"]["active_alerts"] == 1
    assert payload["counts"]["active_hotlists"] == 1
    assert payload["health"]["service"] == "api"
    assert payload["alerts"][0]["alert_id"] == "alert_002"
    assert payload["detections"][0]["detection_id"] == "det_20260320_000002"
    assert payload["hotlists"][0]["entry_id"] == "hl_002"
    assert payload["popup_activity"][0]["event_type"] == "address"
    assert payload["popup_activity"][0]["source_record_id"] == "det_20260320_000002"
    assert payload["popup_activity"][1]["event_type"] == "hotlist"
    assert payload["popup_activity"][1]["source_record_id"] == "alert_002"
