from __future__ import annotations

import time

from fastapi.testclient import TestClient
from PIL import Image

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.config.loader import load_deployment_config
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
    assert crop_response.status_code == 404


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

    delete_response = client.delete(f"/hotlists/{created['entry_id']}")
    assert delete_response.status_code == 204

    deleted_list_response = client.get("/hotlists")
    assert deleted_list_response.status_code == 200
    assert deleted_list_response.json() == []


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
    operator_assignment_create = client.post(
        "/api/v1/assignments",
        headers={"X-RepoScan-Api-Key": "operator-demo-token"},
        json={"detection_id": "det_20260320_000001", "status": "queued", "priority": "priority"},
    )
    public_health = client.get("/api/v1/health")

    assert unauthenticated.status_code == 401
    assert viewer_read.status_code == 200
    assert viewer_hotlist_create.status_code == 403
    assert operator_review.status_code == 201
    assert viewer_follow_up_create.status_code == 403
    assert operator_assignment_create.status_code == 201
    assert public_health.status_code == 200


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
