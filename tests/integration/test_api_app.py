from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from urllib.error import URLError

from fastapi.testclient import TestClient
from PIL import Image

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord
from reposcan_contracts.hotlist import HotlistEntry
import reposcan_api.app as api_app_module
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


def _secure_deployment(tmp_path, *, requests_per_minute: int = 120) -> DeploymentConfig:
    deployment = load_deployment_config("configs/deployments/local-secure-api-example.yaml")
    payload = deployment.model_dump(mode="json")
    payload["api"]["audit"]["log_root"] = str(tmp_path / "api-audit")
    payload["api"]["rate_limit"]["requests_per_minute"] = requests_per_minute
    return DeploymentConfig.model_validate(payload)


def _secure_seeded_client(tmp_path, *, requests_per_minute: int = 120) -> tuple[TestClient, StorageService]:
    repository = InMemoryStorageRepository()
    deployment = _secure_deployment(tmp_path, requests_per_minute=requests_per_minute)
    service = StorageService(
        repository=repository,
        media_root=tmp_path / "media",
        deployment_config=deployment,
    )
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_000001",
                "timestamp_utc": "2026-03-20T04:10:00Z",
                "camera_id": "cam_north_gate_01",
                "gps_latitude": 37.42052,
                "gps_longitude": -122.08091,
                "plate_text": "6BZN220",
                "plate_confidence": 0.95,
                "vehicle_color": "white",
                "vehicle_make": "toyota",
                "vehicle_model": "camry",
                "optional_vehicle_year": "2019",
                "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
                "image_path": "media/frames/cam_north_gate_01/frame_000542.jpg",
                "frame_number": 542,
            }
        )
    )
    client = TestClient(create_app(storage_service=service, deployment_config=deployment))
    return client, service


def _write_demo_image(path, *, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (96, 64), color=color)
    image.save(path, format="JPEG")


def _wait_for_demo_run_completion(client: TestClient, timeout_s: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = client.get("/demo/runtime").json()
        if payload["state"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for demo runtime completion")


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


def test_detection_media_endpoints_serve_frame_and_plate_crop(tmp_path):
    client, service = _seeded_client(tmp_path)
    frame_path = tmp_path / "media" / "frames" / "cam_north_gate_01" / "frame_000542.jpg"
    crop_path = tmp_path / "media" / "crops" / "cam_north_gate_01" / "plate_000542.jpg"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    _write_demo_image(frame_path, color=(24, 24, 24))
    _write_demo_image(crop_path, color=(220, 220, 220))
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_media_001",
                "timestamp_utc": "2026-03-20T04:11:00Z",
                "camera_id": "cam_north_gate_01",
                "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
                "image_path": str(frame_path),
                "plate_crop_path": str(crop_path),
                "frame_number": 543,
            }
        )
    )

    frame_response = client.get("/detections/det_media_001/frame")
    crop_response = client.get("/detections/det_media_001/plate-crop")

    assert frame_response.status_code == 200
    assert frame_response.headers["content-type"].startswith("image/jpeg")
    assert crop_response.status_code == 200
    assert crop_response.headers["content-type"].startswith("image/jpeg")


def test_missing_detection_media_returns_404(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_media_missing",
                "timestamp_utc": "2026-03-20T04:11:00Z",
                "camera_id": "cam_north_gate_01",
                "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
                "image_path": str(tmp_path / "missing" / "frame.jpg"),
                "plate_crop_path": str(tmp_path / "missing" / "crop.jpg"),
                "frame_number": 543,
            }
        )
    )

    frame_response = client.get("/detections/det_media_missing/frame")
    crop_response = client.get("/detections/det_media_missing/plate-crop")

    assert frame_response.status_code == 404
    assert crop_response.status_code == 409
    assert crop_response.json()["detail"] == "Plate crop unavailable"


def test_missing_detection_returns_404(tmp_path):
    client, _ = _seeded_client(tmp_path)

    response = client.get("/detections/does-not-exist")

    assert response.status_code == 404


def test_follow_up_and_assignment_list_and_detail_endpoints(tmp_path):
    client, _ = _seeded_client(tmp_path)

    follow_up_response = client.post(
        "/follow-ups",
        json={
            "detection_id": "det_20260320_000001",
            "plate_text": "6BZN220",
            "priority": "priority",
            "status": "open",
            "summary": "Watch for a repeat sighting near the lot exit.",
        },
    )
    assignment_response = client.post(
        "/assignments",
        json={
            "detection_id": "det_20260320_000001",
            "plate_text": "6BZN220",
            "priority": "priority",
            "status": "queued",
            "assigned_unit_label": "Truck 7",
            "destination_label": "North overflow lot",
            "summary": "Hold tow unit near the likely exit path.",
        },
    )

    assert follow_up_response.status_code == 201
    assert assignment_response.status_code == 201

    follow_up_id = follow_up_response.json()["follow_up_id"]
    assignment_id = assignment_response.json()["assignment_id"]

    follow_up_list = client.get("/follow-ups", params={"detection_id": "det_20260320_000001"})
    follow_up_detail = client.get(f"/follow-ups/{follow_up_id}")
    assignment_list = client.get("/assignments", params={"detection_id": "det_20260320_000001"})
    assignment_detail = client.get(f"/assignments/{assignment_id}")

    assert follow_up_list.status_code == 200
    assert follow_up_detail.status_code == 200
    assert assignment_list.status_code == 200
    assert assignment_detail.status_code == 200
    assert follow_up_list.json()[0]["follow_up_id"] == follow_up_id
    assert follow_up_detail.json()["summary"] == "Watch for a repeat sighting near the lot exit."
    assert assignment_list.json()[0]["assignment_id"] == assignment_id
    assert assignment_detail.json()["assigned_unit_label"] == "Truck 7"


def test_dashboard_overview_uses_expanded_supporting_record_limit(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_north_gate_fresh",
                "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "camera_id": "cam_north_gate_01",
                "vehicle_bbox": {"x": 410, "y": 220, "w": 300, "h": 184},
                "image_path": "media/frames/cam_north_gate_01/frame_fresh.jpg",
                "frame_number": 999,
            }
        )
    )

    for index in range(25):
        service.create_hotlist(
            HotlistEntry.model_validate(
                {
                    "entry_id": f"hl_bulk_{index:03d}",
                    "plate_text": f"8ABC{index:03d}",
                    "label": f"Case {index:03d}",
                    "active": True,
                    "created_at_utc": "2026-03-20T04:00:00Z",
                    "updated_at_utc": "2026-03-20T04:00:00Z",
                }
            )
        )
        service.create_follow_up(
            FollowUpRecord.model_validate(
                {
                    "follow_up_id": f"fu_bulk_{index:03d}",
                    "detection_id": "det_20260320_000001",
                    "plate_text": "6BZN220",
                    "priority": "priority",
                    "status": "open",
                    "created_by_operator_id": "operator_demo",
                    "summary": f"Bulk follow-up {index:03d}",
                    "created_at_utc": "2026-03-20T04:00:00Z",
                    "updated_at_utc": "2026-03-20T04:00:00Z",
                }
            )
        )

    response = client.get("/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["hotlists"]) == 25
    assert len(payload["follow_ups"]) == 25
    assert payload["counts"]["active_hotlists"] == 25
    assert payload["counts"]["open_follow_ups"] == 25


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
    client.post(
        "/reviews/det_20260320_000001",
        json={
            "action": "flag",
            "reviewed_at_utc": "2026-03-20T04:17:00Z",
            "notes": "Need another look before confirming.",
        },
    )

    response = client.get("/reviews/det_20260320_000001")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["action"] == "flag"
    assert payload[0]["notes"] == "Need another look before confirming."
    assert payload[1]["corrected_plate_text"] == "8XYZ999"


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
            "vin": "1hgcm82633a004352",
            "vehicle_year": "2019",
            "vehicle_make": "Honda",
            "vehicle_model": "Accord",
            "vehicle_color": "Black",
            "address_label": "Debtor home",
            "address_line1": "123 Main St",
            "address_city": "Chicago",
            "address_state": "il",
            "address_postal_code": "60607",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["plate_text"] == "8ABC123"
    assert created["vin"] == "1HGCM82633A004352"
    assert created["vehicle_make"] == "Honda"
    assert created["address_state"] == "IL"

    list_response = client.get("/hotlists")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = client.put(
        f"/hotlists/{created['entry_id']}",
        json={
            "plate_text": "8ABC123",
            "label": "Case 42 Updated",
            "notes": "Escalated",
            "vin": "1hgcm82633a004352",
            "vehicle_year": "2020",
            "vehicle_make": "Honda",
            "vehicle_model": "Accord",
            "vehicle_color": "Black",
            "address_label": "Impound watch",
            "address_line1": "456 State St",
            "address_city": "Chicago",
            "address_state": "il",
            "address_postal_code": "60616",
            "active": False,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Case 42 Updated"
    assert updated["active"] is False
    assert updated["address_line1"] == "456 State St"

    vin_only_response = client.post(
        "/hotlists",
        json={
            "vin": "2fmhk6dt8kba12345",
            "vehicle_year": "2019",
            "vehicle_make": "Ford",
            "vehicle_model": "Explorer",
            "address_line1": "789 Lake Shore Dr",
            "address_city": "Chicago",
            "address_state": "IL",
            "label": "VIN intake",
            "notes": "Awaiting confirmed plate.",
            "active": True,
        },
    )
    assert vin_only_response.status_code == 201
    assert vin_only_response.json()["plate_text"] is None

    delete_response = client.delete(f"/hotlists/{created['entry_id']}")
    assert delete_response.status_code == 204

    deleted_list_response = client.get("/hotlists")
    assert deleted_list_response.status_code == 200
    remaining_entries = deleted_list_response.json()
    assert len(remaining_entries) == 1
    assert remaining_entries[0]["vin"] == "2FMHK6DT8KBA12345"


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


def test_put_alert_updates_status_and_popup_note(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_001",
                "plate_text": "8ABC123",
                "label": "Case 42",
                "created_at_utc": "2026-03-20T04:00:00Z",
                "updated_at_utc": "2026-03-20T04:00:00Z",
            }
        )
    )
    service.store_alert(
        AlertRecord.model_validate(
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
    )

    response = client.put(
        "/alerts/alert_001",
        json={
            "status": "acknowledged",
            "operator_id": "cab_demo_01",
            "response_notes": "Operator confirmed the vehicle and is holding position.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "acknowledged"
    assert payload["response_operator_id"] == "cab_demo_01"
    assert payload["response_notes"] == "Operator confirmed the vehicle and is holding position."
    assert payload["updated_at_utc"].endswith("Z")
    assert service.get_alert("alert_001").status == "acknowledged"

    overview = client.get("/dashboard/overview").json()
    popup_event = next(event for event in overview["popup_activity"] if event["source_record_id"] == "alert_001")
    assert popup_event["note"] == "Operator confirmed the vehicle and is holding position."


def test_dismissed_alert_is_removed_from_popup_activity(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_000002",
                "timestamp_utc": "2026-03-20T04:22:00Z",
                "camera_id": "cam_lot_east_03",
                "vehicle_bbox": {"x": 404, "y": 218, "w": 314, "h": 186},
                "image_path": "media/frames/cam_lot_east_03/frame_000644.jpg",
                "frame_number": 644,
            }
        )
    )
    service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_002",
                "plate_text": "8ABC123",
                "label": "Dismissed target",
                "created_at_utc": "2026-03-20T04:00:00Z",
                "updated_at_utc": "2026-03-20T04:00:00Z",
            }
        )
    )
    service.store_alert(
        AlertRecord.model_validate(
            {
                "alert_id": "alert_002",
                "detection_id": "det_20260320_000001",
                "hotlist_entry_id": "hl_002",
                "timestamp_utc": "2026-03-20T04:21:00Z",
                "camera_id": "cam_north_gate_01",
                "matched_plate_text": "8ABC123",
                "match_confidence": 0.95,
                "match_type": "exact",
                "hotlist_label": "Dismissed target",
                "status": "dismissed",
                "response_notes": "Stand down recorded after visual mismatch.",
                "updated_at_utc": "2026-03-20T04:23:00Z",
            }
        )
    )

    response = client.get("/dashboard/overview")

    assert response.status_code == 200
    popup_source_ids = {event["source_record_id"] for event in response.json()["popup_activity"]}
    assert "alert_002" not in popup_source_ids
    assert "det_20260320_000001" not in popup_source_ids
    assert "det_20260320_000002" in popup_source_ids


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
    assert payload["counts"]["open_follow_ups"] == 0
    assert payload["counts"]["active_assignments"] == 0
    assert payload["counts"]["active_sessions"] == 0
    assert payload["health"]["service"] == "api"
    assert payload["alerts"][0]["alert_id"] == "alert_002"
    assert payload["detections"][0]["detection_id"] == "det_20260320_000002"
    assert payload["hotlists"][0]["entry_id"] == "hl_002"
    assert payload["current_principal"]["principal_id"] == "local_dev"
    assert payload["current_principal"]["capabilities"]["can_manage_dispatch"] is True
    assert payload["current_principal"]["capabilities"]["can_control_edge_runtime"] is True
    assert payload["follow_ups"] == []
    assert payload["assignments"] == []
    assert payload["active_sessions"] == []
    assert payload["popup_activity"][0]["event_type"] == "address"
    assert payload["popup_activity"][0]["source_record_id"] == "det_20260320_000002"
    assert payload["popup_activity"][1]["event_type"] == "hotlist"
    assert payload["popup_activity"][1]["source_record_id"] == "alert_002"


def test_follow_up_assignment_and_operator_presence_surface_in_dashboard(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_follow_up",
                "plate_text": "6BZN220",
                "label": "Pinned target",
                "created_at_utc": "2026-03-20T04:00:00Z",
                "updated_at_utc": "2026-03-20T04:00:00Z",
            }
        )
    )
    service.store_alert(
        AlertRecord.model_validate(
            {
                "alert_id": "alert_follow_up",
                "detection_id": "det_20260320_000001",
                "hotlist_entry_id": "hl_follow_up",
                "timestamp_utc": "2026-03-20T04:20:00Z",
                "camera_id": "cam_north_gate_01",
                "matched_plate_text": "6BZN220",
                "match_confidence": 0.95,
                "match_type": "exact",
                "hotlist_label": "Pinned target",
            }
        )
    )

    session_response = client.post(
        "/operator/sessions/heartbeat",
        json={
            "session_id": "session_001",
            "client_label": "cab_console_01",
            "workspace": "alerts",
            "selected_detection_id": "det_20260320_000001",
            "selected_alert_id": "alert_follow_up",
            "destination_label": "Shoreline Marina south lot",
            "arrival_radius_feet": 50,
            "idle_scan_enabled": False,
            "visible_map_layers": ["active_alerts", "historical_alerts", "detections"],
            "navigation_active": True,
        },
    )
    follow_up_response = client.post(
        "/follow-ups",
        json={
            "detection_id": "det_20260320_000001",
            "alert_id": "alert_follow_up",
            "plate_text": "6BZN220",
            "priority": "critical",
            "status": "open",
            "assigned_operator_id": "tow_lead_02",
            "summary": "Pin the target until the tow team is on scene.",
        },
    )
    assignment_response = client.post(
        "/assignments",
        json={
            "detection_id": "det_20260320_000001",
            "alert_id": "alert_follow_up",
            "plate_text": "6BZN220",
            "priority": "critical",
            "status": "en_route",
            "assigned_operator_id": "tow_lead_02",
            "assigned_unit_label": "Truck 4",
            "destination_label": "Shoreline Marina south lot",
            "summary": "Dispatch tow team toward the pinned Camry.",
        },
    )

    overview = client.get("/dashboard/overview")

    assert session_response.status_code == 200
    assert follow_up_response.status_code == 201
    assert assignment_response.status_code == 201
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["counts"]["open_follow_ups"] == 1
    assert payload["counts"]["active_assignments"] == 1
    assert payload["counts"]["active_sessions"] == 1
    assert payload["follow_ups"][0]["summary"] == "Pin the target until the tow team is on scene."
    assert payload["assignments"][0]["assigned_unit_label"] == "Truck 4"
    assert payload["active_sessions"][0]["workspace"] == "alerts"
    assert payload["active_sessions"][0]["destination_label"] == "Shoreline Marina south lot"
    assert payload["active_sessions"][0]["arrival_radius_feet"] == 50
    assert payload["active_sessions"][0]["visible_map_layers"] == ["active_alerts", "historical_alerts", "detections"]
    assert service.list_operator_sessions(limit=10)[0].session_id == "session_001"


def test_demo_runtime_endpoints_run_headless_ingest_and_update_dashboard(tmp_path):
    client, service = _seeded_client(tmp_path)
    frames_dir = tmp_path / "demo_frames"
    frames_dir.mkdir()
    for index, color in enumerate(((12, 12, 12), (16, 16, 16), (20, 20, 20)), start=1):
        _write_demo_image(frames_dir / f"frame_{index:04d}.jpg", color=color)

    service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_demo_runtime",
                "plate_text": "6BZN220",
                "label": "Demo runtime target",
                "created_at_utc": "2026-03-20T04:00:00Z",
                "updated_at_utc": "2026-03-20T04:00:00Z",
            }
        )
    )

    idle_response = client.get("/demo/runtime")
    assert idle_response.status_code == 200
    assert idle_response.json()["state"] == "idle"

    start_response = client.post(
        "/demo/runs",
        json={
            "frames_directory": str(frames_dir),
            "frame_interval_ms": 100.0,
            "sequence_id": "seq_api_demo",
            "plate_text": "6BZN220",
        },
    )

    assert start_response.status_code == 202
    assert start_response.json()["state"] == "running"

    completed = _wait_for_demo_run_completion(client)
    assert completed["state"] == "succeeded"
    assert completed["summary"]["frames_captured"] == 3
    assert len(completed["summary"]["stored_detection_ids"]) == 1
    assert len(completed["summary"]["created_alert_ids"]) == 1

    overview = client.get("/dashboard/overview").json()
    assert completed["summary"]["stored_detection_ids"][0] in {
        record["detection_id"] for record in overview["detections"]
    }
    assert completed["summary"]["created_alert_ids"][0] in {
        record["alert_id"] for record in overview["alerts"]
    }
    camera_health = {record["camera_id"]: record for record in overview["camera_health"]}
    assert camera_health["cam_north_gate_01"]["status"] == "offline"
    assert camera_health["cam_north_gate_01"]["label"] == "North Gate Camera 1"
    assert camera_health["cam_file_demo_01"]["status"] == "online"


def test_demo_runtime_reports_failures_for_missing_frame_folder(tmp_path):
    client, _ = _seeded_client(tmp_path)

    start_response = client.post(
        "/demo/runs",
        json={
            "frames_directory": str(tmp_path / "missing_frames"),
            "sequence_id": "seq_missing",
            "plate_text": "6BZN220",
        },
    )

    assert start_response.status_code == 202
    completed = _wait_for_demo_run_completion(client)
    assert completed["state"] == "failed"
    assert "No frame files found" in completed["error_message"]


def test_edge_runtime_status_command_and_heartbeat_flow(tmp_path):
    client, _ = _seeded_client(tmp_path)

    initial = client.get("/edge/runtime")
    assert initial.status_code == 200
    assert initial.json()["desired_capture_state"] == "stopped"

    command_response = client.post(
        "/edge/runtime/command",
        json={
            "command": "start_capture",
            "operator_id": "driver_01",
            "reason": "Begin route scan",
        },
    )
    assert command_response.status_code == 200
    commanded = command_response.json()
    assert commanded["capture_state"] == "starting"
    assert commanded["desired_capture_state"] == "running"
    assert commanded["last_command"] == "start_capture"
    assert commanded["last_commanded_by"] == "driver_01"

    heartbeat_response = client.post(
        "/edge/runtime/heartbeat",
        json={
            "edge_node_id": "jetson_orin_nano_truck_01",
            "capture_state": "running",
            "active_camera_count": 2,
            "total_camera_count": 2,
            "inference_runtime": "jetson-pytorch-onnxruntime",
            "plate_ocr_provider": "fast-alpr",
            "vehicle_attribute_provider": "hf_vehicle_classifier",
            "message": "Capture loop healthy",
        },
    )
    assert heartbeat_response.status_code == 200
    heartbeat = heartbeat_response.json()
    assert heartbeat["edge_node_id"] == "jetson_orin_nano_truck_01"
    assert heartbeat["capture_state"] == "running"
    assert heartbeat["desired_capture_state"] == "running"
    assert heartbeat["active_camera_count"] == 2
    assert heartbeat["last_heartbeat_at_utc"] is not None


def test_versioned_routes_and_security_headers_work_with_legacy_aliases(tmp_path):
    client, _ = _seeded_client(tmp_path)

    legacy = client.get("/health")
    versioned = client.get("/api/v1/health")
    version_info = client.get("/api/v1/version")

    assert legacy.status_code == 200
    assert versioned.status_code == 200
    assert version_info.status_code == 200
    assert versioned.headers["x-api-version"] == "v1"
    assert "x-request-id" in {key.lower() for key in versioned.headers.keys()}
    assert versioned.headers["cache-control"] == "no-store"
    assert version_info.json()["canonical_prefix"] == "/api/v1"
    assert version_info.json()["legacy_routes_enabled"] is True


def test_versioned_detection_search_supports_plate_time_gps_vehicle_and_alert_filters(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_search_match",
                "timestamp_utc": "2026-03-20T04:11:00Z",
                "camera_id": "cam_north_gate_01",
                "gps_latitude": 37.42055,
                "gps_longitude": -122.08095,
                "plate_text": "6BZN220",
                "plate_confidence": 0.94,
                "vehicle_color": "white",
                "vehicle_make": "toyota",
                "vehicle_model": "camry",
                "optional_vehicle_year": "2019",
                "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
                "image_path": "media/frames/cam_north_gate_01/frame_000543.jpg",
                "frame_number": 543,
            }
        )
    )
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_search_other",
                "timestamp_utc": "2026-03-20T04:12:00Z",
                "camera_id": "cam_lot_east_03",
                "gps_latitude": 35.10000,
                "gps_longitude": -120.20000,
                "plate_text": "8XYZ999",
                "plate_confidence": 0.74,
                "vehicle_color": "black",
                "vehicle_make": "ford",
                "vehicle_model": "focus",
                "optional_vehicle_year": "2015",
                "vehicle_bbox": {"x": 404, "y": 218, "w": 314, "h": 186},
                "image_path": "media/frames/cam_lot_east_03/frame_000644.jpg",
                "frame_number": 644,
            }
        )
    )
    service.create_hotlist(
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_search",
                "plate_text": "6BZN220",
                "label": "Search target",
                "created_at_utc": "2026-03-20T04:00:00Z",
                "updated_at_utc": "2026-03-20T04:00:00Z",
            }
        )
    )
    service.store_alert(
        AlertRecord.model_validate(
            {
                "alert_id": "alert_search",
                "detection_id": "det_search_match",
                "hotlist_entry_id": "hl_search",
                "timestamp_utc": "2026-03-20T04:11:30Z",
                "camera_id": "cam_north_gate_01",
                "matched_plate_text": "6BZN220",
                "match_confidence": 0.95,
                "match_type": "exact",
                "hotlist_label": "Search target",
                "status": "acknowledged",
                "response_operator_id": "search_operator",
                "updated_at_utc": "2026-03-20T04:12:00Z",
            }
        )
    )

    detection_response = client.get(
        "/api/v1/search/detections",
        params={
            "plate": "BZN",
            "plate_match": "contains",
            "start_utc": "2026-03-20T04:10:30Z",
            "end_utc": "2026-03-20T04:11:30Z",
            "camera_id": "cam_north_gate_01",
            "min_latitude": 37.42,
            "max_latitude": 37.43,
            "min_longitude": -122.09,
            "max_longitude": -122.07,
            "vehicle_color": "white",
            "vehicle_make": "toyota",
            "vehicle_model": "camry",
            "vehicle_year": "2019",
            "alert_status": "acknowledged",
        },
    )
    alert_response = client.get(
        "/api/v1/search/alerts",
        params={
            "plate": "6BZN",
            "plate_match": "prefix",
            "status": "acknowledged",
            "vehicle_make": "toyota",
            "camera_id": "cam_north_gate_01",
        },
    )

    assert detection_response.status_code == 200
    detection_payload = detection_response.json()
    assert detection_payload["page"]["total_results"] == 1
    assert detection_payload["results"][0]["detection_id"] == "det_search_match"

    assert alert_response.status_code == 200
    alert_payload = alert_response.json()
    assert alert_payload["page"]["total_results"] == 1
    assert alert_payload["results"][0]["alert_id"] == "alert_search"


def test_versioned_search_supports_geo_circle_and_polygon_filters(tmp_path):
    client, service = _seeded_client(tmp_path)
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_geo_match",
                "timestamp_utc": "2026-03-20T04:13:00Z",
                "camera_id": "cam_north_gate_01",
                "gps_latitude": 37.42052,
                "gps_longitude": -122.08091,
                "plate_text": "6BZN220",
                "plate_confidence": 0.94,
                "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
                "image_path": "media/frames/cam_north_gate_01/frame_000544.jpg",
                "frame_number": 544,
            }
        )
    )
    service.store_detection(
        DetectionRecord.model_validate(
            {
                "detection_id": "det_geo_other",
                "timestamp_utc": "2026-03-20T04:14:00Z",
                "camera_id": "cam_lot_east_03",
                "gps_latitude": 35.10000,
                "gps_longitude": -120.20000,
                "plate_text": "8XYZ999",
                "plate_confidence": 0.74,
                "vehicle_bbox": {"x": 404, "y": 218, "w": 314, "h": 186},
                "image_path": "media/frames/cam_lot_east_03/frame_000645.jpg",
                "frame_number": 645,
            }
        )
    )
    service.store_alert(
        AlertRecord.model_validate(
            {
                "alert_id": "alert_geo_match",
                "detection_id": "det_geo_match",
                "hotlist_entry_id": "hl_search",
                "timestamp_utc": "2026-03-20T04:13:30Z",
                "camera_id": "cam_north_gate_01",
                "matched_plate_text": "6BZN220",
                "match_confidence": 0.95,
                "match_type": "exact",
                "hotlist_label": "Search target",
                "gps_latitude": 37.42052,
                "gps_longitude": -122.08091,
            }
        )
    )

    circle_response = client.get(
        "/api/v1/search/detections",
        params={
            "geo_shape": "circle",
            "geo_center_latitude": 37.42052,
            "geo_center_longitude": -122.08091,
            "geo_radius_meters": 100.0,
        },
    )
    polygon_response = client.get(
        "/api/v1/search/alerts",
        params=[
            ("geo_shape", "polygon"),
            ("geo_polygon_latitude", 37.42040),
            ("geo_polygon_latitude", 37.42040),
            ("geo_polygon_latitude", 37.42070),
            ("geo_polygon_latitude", 37.42070),
            ("geo_polygon_longitude", -122.08110),
            ("geo_polygon_longitude", -122.08070),
            ("geo_polygon_longitude", -122.08070),
            ("geo_polygon_longitude", -122.08110),
        ],
    )

    assert circle_response.status_code == 200
    assert circle_response.json()["page"]["total_results"] == 1
    assert circle_response.json()["results"][0]["detection_id"] == "det_geo_match"
    assert polygon_response.status_code == 200
    assert polygon_response.json()["page"]["total_results"] == 1
    assert polygon_response.json()["results"][0]["alert_id"] == "alert_geo_match"


def test_versioned_address_search_returns_provider_results_and_writes_audit_event(tmp_path, monkeypatch):
    client, _ = _secure_seeded_client(tmp_path)
    viewer_headers = {"X-RepoScan-Api-Key": "viewer-demo-token"}
    admin_headers = {"X-RepoScan-Api-Key": "admin-demo-token"}
    captured: dict[str, object] = {}

    def fake_search(
        query: str,
        *,
        limit: int,
        countrycodes: str = "us",
        bias_latitude: float | None = None,
        bias_longitude: float | None = None,
    ):
        captured["query"] = query
        captured["limit"] = limit
        captured["countrycodes"] = countrycodes
        captured["bias_latitude"] = bias_latitude
        captured["bias_longitude"] = bias_longitude
        return [
            api_app_module.AddressSearchSuggestion(
                suggestion_id="place_001",
                display_name="ABC Towing, 4128 W Fulton St, Cook County, Illinois",
                latitude=41.8862,
                longitude=-87.7282,
                provider="nominatim",
            )
        ]

    monkeypatch.setattr(api_app_module, "_search_address_candidates", fake_search)

    response = client.get(
        "/api/v1/search/addresses",
        headers=viewer_headers,
        params={"q": "4128 W Fulton St", "limit": 3, "bias_latitude": 35.4676, "bias_longitude": -97.5164},
    )
    audit_response = client.get("/api/v1/audit/events", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["display_name"] == "ABC Towing, 4128 W Fulton St, Cook County, Illinois"
    assert payload["results"][0]["latitude"] == 41.8862
    assert payload["results"][0]["longitude"] == -87.7282
    assert captured == {
        "query": "4128 W Fulton St",
        "limit": 3,
        "countrycodes": "us",
        "bias_latitude": 35.4676,
        "bias_longitude": -97.5164,
    }

    assert audit_response.status_code == 200
    actions = [event["action"] for event in audit_response.json()["events"]]
    assert "search.addresses" in actions


def test_versioned_address_search_returns_502_when_provider_fails(tmp_path, monkeypatch):
    client, _ = _secure_seeded_client(tmp_path)
    viewer_headers = {"X-RepoScan-Api-Key": "viewer-demo-token"}

    def fake_search(
        query: str,
        *,
        limit: int,
        countrycodes: str = "us",
        bias_latitude: float | None = None,
        bias_longitude: float | None = None,
    ):
        raise api_app_module.AddressSearchProviderError("provider down")

    monkeypatch.setattr(api_app_module, "_search_address_candidates", fake_search)

    response = client.get(
        "/api/v1/search/addresses",
        headers=viewer_headers,
        params={"q": "4128 W Fulton St"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Address search unavailable"


def test_versioned_reverse_address_returns_current_location_context_and_writes_audit_event(tmp_path, monkeypatch):
    client, _ = _secure_seeded_client(tmp_path)
    viewer_headers = {"X-RepoScan-Api-Key": "viewer-demo-token"}
    admin_headers = {"X-RepoScan-Api-Key": "admin-demo-token"}
    captured: dict[str, float] = {}

    def fake_reverse(latitude: float, longitude: float):
        captured["latitude"] = latitude
        captured["longitude"] = longitude
        return api_app_module.ReverseAddressResponse(
            display_name="4128 W Fulton St, Chicago, Illinois",
            latitude=latitude,
            longitude=longitude,
            house_number="4128",
            road="W Fulton St",
            city="Chicago",
            state="Illinois",
            postal_code="60624",
            provider="nominatim",
        )

    monkeypatch.setattr(api_app_module, "_reverse_address_lookup", fake_reverse)

    response = client.get(
        "/api/v1/search/reverse-address",
        headers=viewer_headers,
        params={"latitude": 41.8862, "longitude": -87.7282},
    )
    audit_response = client.get("/api/v1/audit/events", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["house_number"] == "4128"
    assert payload["road"] == "W Fulton St"
    assert payload["display_name"] == "4128 W Fulton St, Chicago, Illinois"
    assert captured == {"latitude": 41.8862, "longitude": -87.7282}
    assert audit_response.status_code == 200
    actions = [event["action"] for event in audit_response.json()["events"]]
    assert "search.reverse_address" in actions


def test_versioned_reverse_address_returns_502_when_provider_fails(tmp_path, monkeypatch):
    client, _ = _secure_seeded_client(tmp_path)
    viewer_headers = {"X-RepoScan-Api-Key": "viewer-demo-token"}

    def fake_reverse(latitude: float, longitude: float):
        raise api_app_module.AddressSearchProviderError("provider down")

    monkeypatch.setattr(api_app_module, "_reverse_address_lookup", fake_reverse)

    response = client.get(
        "/api/v1/search/reverse-address",
        headers=viewer_headers,
        params={"latitude": 41.8862, "longitude": -87.7282},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Reverse address lookup unavailable"


def test_versioned_address_search_allows_unauthenticated_requests(tmp_path, monkeypatch):
    client, _ = _secure_seeded_client(tmp_path)

    def fake_search(
        query: str,
        *,
        limit: int,
        countrycodes: str = "us",
        bias_latitude: float | None = None,
        bias_longitude: float | None = None,
    ):
        assert query == "4128 W Fulton St"
        assert limit == 2
        return [
            api_app_module.AddressSearchSuggestion(
                suggestion_id="place_public",
                display_name="ABC Towing, 4128 W Fulton St, Cook County, Illinois",
                latitude=41.8862,
                longitude=-87.7282,
                provider="nominatim",
            )
        ]

    monkeypatch.setattr(api_app_module, "_search_address_candidates", fake_search)

    response = client.get(
        "/api/v1/search/addresses",
        params={"q": "4128 W Fulton St", "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["display_name"] == "ABC Towing, 4128 W Fulton St, Cook County, Illinois"


def test_address_search_candidates_reuses_fresh_cache(monkeypatch):
    api_app_module._address_search_cache.clear()
    calls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "place_id": 101,
                        "display_name": "ABC Towing, 4128 W Fulton St, Tulsa County, Oklahoma",
                        "lat": "36.1540",
                        "lon": "-95.9928",
                        "address": {"house_number": "4128", "road": "West Fulton Street", "city": "Tulsa", "state": "Oklahoma"},
                    }
                ]
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse()

    monotonic_values = iter([100.0, 120.0])
    monkeypatch.setattr(api_app_module, "urlopen", fake_urlopen)
    monkeypatch.setattr(api_app_module.time, "monotonic", lambda: next(monotonic_values))

    first = api_app_module._search_address_candidates("4128 W Fulton St", limit=5)
    second = api_app_module._search_address_candidates("4128 W Fulton St", limit=5)

    assert len(calls) == 1
    assert first[0].display_name == second[0].display_name
    api_app_module._address_search_cache.clear()


def test_address_search_candidates_returns_stale_cache_when_provider_fails(monkeypatch):
    api_app_module._address_search_cache.clear()
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "place_id": 202,
                        "display_name": "ABC Towing, 4128 W Fulton St, Tulsa County, Oklahoma",
                        "lat": "36.1540",
                        "lon": "-95.9928",
                        "address": {"house_number": "4128", "road": "West Fulton Street", "city": "Tulsa", "state": "Oklahoma"},
                    }
                ]
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse()
        raise URLError("provider down")

    monotonic_values = iter([100.0, 450.0, 450.0])
    monkeypatch.setattr(api_app_module, "urlopen", fake_urlopen)
    monkeypatch.setattr(api_app_module.time, "monotonic", lambda: next(monotonic_values))

    first = api_app_module._search_address_candidates("4128 W Fulton St", limit=5)
    second = api_app_module._search_address_candidates("4128 W Fulton St", limit=5)

    assert calls["count"] == 2
    assert second[0].display_name == first[0].display_name
    api_app_module._address_search_cache.clear()


def test_address_search_candidates_filters_to_texas_and_oklahoma(monkeypatch):
    api_app_module._address_search_cache.clear()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "place_id": 301,
                        "display_name": "4128 West Fulton Street, Broken Arrow, Tulsa, Oklahoma, 74012, United States",
                        "lat": "36.0234901",
                        "lon": "-95.8405338",
                        "address": {"house_number": "4128", "road": "West Fulton Street", "city": "Broken Arrow", "state": "Oklahoma"},
                    },
                    {
                        "place_id": 302,
                        "display_name": "4128 West Fulton Street, Los Angeles, California, 90012, United States",
                        "lat": "34.052235",
                        "lon": "-118.243683",
                        "address": {"house_number": "4128", "road": "West Fulton Street", "city": "Los Angeles", "state": "California"},
                    },
                ]
            ).encode("utf-8")

    monkeypatch.setattr(api_app_module, "urlopen", lambda request, timeout: FakeResponse())
    results = api_app_module._search_address_candidates("4128 W Fulton St", limit=5)

    assert [item.display_name for item in results] == [
        "4128 West Fulton Street, Broken Arrow, Tulsa, Oklahoma, 74012, United States"
    ]
    api_app_module._address_search_cache.clear()


def test_address_search_candidates_retries_with_spelling_variant(monkeypatch):
    api_app_module._address_search_cache.clear()
    calls: list[str] = []

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"[]"

    class MatchResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                [
                    {
                        "place_id": 401,
                        "display_name": "920, North Virginia Drive, Oklahoma City, Oklahoma County, Oklahoma, 73107, United States",
                        "lat": "35.4766259",
                        "lon": "-97.5976956",
                        "address": {"house_number": "920", "road": "North Virginia Drive", "city": "Oklahoma City", "state": "Oklahoma"},
                    }
                ]
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if "virgina" in request.full_url:
            return EmptyResponse()
        return MatchResponse()

    monkeypatch.setattr(api_app_module, "urlopen", fake_urlopen)

    results = api_app_module._search_address_candidates(
        "920 n virgina dr oklahoma city ok",
        limit=5,
        bias_latitude=35.4676,
        bias_longitude=-97.5164,
    )

    assert len(calls) == 2
    assert "virgina" in calls[0]
    assert "virginia" in calls[1]
    assert results[0].display_name == "920, North Virginia Drive, Oklahoma City, Oklahoma County, Oklahoma, 73107, United States"
    api_app_module._address_search_cache.clear()


def test_secure_api_requires_credentials_and_enforces_roles(tmp_path):
    client, _ = _secure_seeded_client(tmp_path)

    unauthenticated = client.get("/api/v1/detections")
    viewer_read = client.get("/api/v1/detections", headers={"X-RepoScan-Api-Key": "viewer-demo-token"})
    viewer_hotlist_create = client.post(
        "/api/v1/hotlists",
        headers={"X-RepoScan-Api-Key": "viewer-demo-token"},
        json={"plate_text": "8ABC123", "label": "Nope", "active": True},
    )
    operator_review = client.post(
        "/api/v1/reviews/det_20260320_000001",
        headers={"X-RepoScan-Api-Key": "operator-demo-token"},
        json={"action": "confirm", "reviewed_at_utc": "2026-03-20T04:15:00Z"},
    )
    viewer_follow_up_create = client.post(
        "/api/v1/follow-ups",
        headers={"X-RepoScan-Api-Key": "viewer-demo-token"},
        json={"detection_id": "det_20260320_000001", "status": "open", "priority": "priority"},
    )
    viewer_follow_up_read = client.get("/api/v1/follow-ups", headers={"X-RepoScan-Api-Key": "viewer-demo-token"})
    viewer_assignment_read = client.get("/api/v1/assignments", headers={"X-RepoScan-Api-Key": "viewer-demo-token"})
    operator_assignment_create = client.post(
        "/api/v1/assignments",
        headers={"X-RepoScan-Api-Key": "operator-demo-token"},
        json={"detection_id": "det_20260320_000001", "status": "queued", "priority": "priority"},
    )
    viewer_edge_status = client.get("/api/v1/edge/runtime", headers={"X-RepoScan-Api-Key": "viewer-demo-token"})
    viewer_edge_command = client.post(
        "/api/v1/edge/runtime/command",
        headers={"X-RepoScan-Api-Key": "viewer-demo-token"},
        json={"command": "start_capture"},
    )
    operator_edge_command = client.post(
        "/api/v1/edge/runtime/command",
        headers={"X-RepoScan-Api-Key": "operator-demo-token"},
        json={"command": "start_capture"},
    )
    operator_edge_heartbeat = client.post(
        "/api/v1/edge/runtime/heartbeat",
        headers={"X-RepoScan-Api-Key": "operator-demo-token"},
        json={"edge_node_id": "truck_01", "capture_state": "running"},
    )
    admin_edge_heartbeat = client.post(
        "/api/v1/edge/runtime/heartbeat",
        headers={"X-RepoScan-Api-Key": "admin-demo-token"},
        json={"edge_node_id": "truck_01", "capture_state": "running"},
    )
    public_health = client.get("/api/v1/health")

    assert unauthenticated.status_code == 401
    assert viewer_read.status_code == 200
    assert viewer_hotlist_create.status_code == 403
    assert operator_review.status_code == 201
    assert viewer_follow_up_create.status_code == 403
    assert viewer_follow_up_read.status_code == 200
    assert viewer_assignment_read.status_code == 200
    assert operator_assignment_create.status_code == 201
    assert viewer_edge_status.status_code == 200
    assert viewer_edge_command.status_code == 403
    assert operator_edge_command.status_code == 200
    assert operator_edge_heartbeat.status_code == 403
    assert admin_edge_heartbeat.status_code == 200
    assert public_health.status_code == 200


def test_api_uses_configured_cors_origins(tmp_path):
    deployment = _secure_deployment(tmp_path)
    payload = deployment.model_dump(mode="json")
    payload["api"]["hardening"]["cors_origins"] = ["https://console.example.test"]
    configured = DeploymentConfig.model_validate(payload)

    repository = InMemoryStorageRepository()
    service = StorageService(
        repository=repository,
        media_root=tmp_path / "media",
        deployment_config=configured,
    )
    client = TestClient(create_app(storage_service=service, deployment_config=configured))

    response = client.options(
        "/api/v1/detections",
        headers={
            "Origin": "https://console.example.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://console.example.test"


def test_secure_api_writes_audit_events_and_exposes_audit_surface(tmp_path):
    client, _ = _secure_seeded_client(tmp_path)
    viewer_headers = {"X-RepoScan-Api-Key": "viewer-demo-token"}
    admin_headers = {"X-RepoScan-Api-Key": "admin-demo-token"}

    search_response = client.get("/api/v1/search/detections", headers=viewer_headers, params={"plate": "6BZN"})
    hotlist_response = client.post(
        "/api/v1/hotlists",
        headers=admin_headers,
        json={"plate_text": "8ABC123", "label": "Case 42", "notes": "Audit test", "active": True},
    )
    audit_response = client.get("/api/v1/audit/events", headers=admin_headers)

    assert search_response.status_code == 200
    assert hotlist_response.status_code == 201
    assert audit_response.status_code == 200
    events = audit_response.json()["events"]
    actions = [event["action"] for event in events]
    assert "hotlist.create" in actions
    assert "search.detections" in actions
    hotlist_event = next(event for event in events if event["action"] == "hotlist.create")
    assert hotlist_event["principal_id"] == "admin_demo"
    assert hotlist_event["target_type"] == "hotlist"


def test_secure_api_rate_limits_repeated_requests(tmp_path):
    client, _ = _secure_seeded_client(tmp_path, requests_per_minute=2)
    headers = {"X-RepoScan-Api-Key": "viewer-demo-token"}

    first = client.get("/api/v1/detections", headers=headers)
    second = client.get("/api/v1/detections", headers=headers)
    third = client.get("/api/v1/detections", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"] == "Rate limit exceeded"
    assert int(third.headers["retry-after"]) >= 1
