from __future__ import annotations

from fastapi.testclient import TestClient

from reposcan_contracts.detection import DetectionRecord
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
