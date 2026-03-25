from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import yaml

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord
from reposcan_storage.json_store import JsonFileStorageRepository
from reposcan_storage.postgres import PostgresStorageRepository
from reposcan_storage.service import create_development_storage_service, create_storage_service_from_deployment


REPO_ROOT = Path(__file__).resolve().parents[2]


def _detection(detection_id: str, timestamp_utc: str, camera_id: str) -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": detection_id,
            "timestamp_utc": timestamp_utc,
            "camera_id": camera_id,
            "vehicle_bbox": {"x": 10, "y": 20, "w": 100, "h": 50},
            "image_path": "media/frames/frame.jpg",
            "frame_number": 1,
        }
    )


def _review() -> ReviewRecord:
    return ReviewRecord.model_validate(
        {
            "review_id": "rev_pg_001",
            "detection_id": "det_pg_001",
            "action": "confirm",
            "reviewed_at_utc": "2026-03-24T20:01:00Z",
        }
    )


def _alert() -> AlertRecord:
    return AlertRecord.model_validate(
        {
            "alert_id": "alert_pg_001",
            "detection_id": "det_pg_001",
            "hotlist_entry_id": "hl_pg_001",
            "timestamp_utc": "2026-03-24T20:02:00Z",
            "camera_id": "cam_pg_01",
            "matched_plate_text": "8ABC123",
            "match_confidence": 0.92,
            "match_type": "exact",
            "hotlist_label": "Postgres case",
        }
    )


def _hotlist() -> HotlistEntry:
    return HotlistEntry.model_validate(
        {
            "entry_id": "hl_pg_001",
            "plate_text": "8ABC123",
            "label": "Postgres case",
            "created_at_utc": "2026-03-24T19:59:00Z",
            "updated_at_utc": "2026-03-24T19:59:00Z",
        }
    )


def test_postgres_storage_repository_roundtrip_in_sqlite_mode():
    repository = PostgresStorageRepository(":memory:", dialect="sqlite")
    detection = _detection("det_pg_001", "2026-03-24T20:00:00Z", "cam_pg_01")
    newer_detection = _detection("det_pg_002", "2026-03-24T20:10:00Z", "cam_pg_02")

    repository.upsert_detection(detection)
    repository.upsert_detection(newer_detection)
    repository.create_review(_review())
    repository.create_alert(_alert())
    repository.upsert_hotlist(_hotlist())

    assert repository.get_detection("det_pg_001") == detection
    assert [item.detection_id for item in repository.list_detections(limit=10)] == ["det_pg_002", "det_pg_001"]
    assert repository.list_detections(camera_id="cam_pg_01", limit=10)[0].detection_id == "det_pg_001"
    assert repository.list_reviews("det_pg_001")[0].review_id == "rev_pg_001"
    assert repository.get_alert("alert_pg_001") is not None
    assert repository.list_alerts(camera_id="cam_pg_01", limit=10)[0].alert_id == "alert_pg_001"
    assert repository.get_hotlist("hl_pg_001") is not None
    assert repository.list_hotlists(active_only=True, limit=10)[0].entry_id == "hl_pg_001"


def test_postgres_storage_repository_requests_postgis_extension():
    executed: list[str] = []

    class RecordingCursor:
        def execute(self, query: str, params: tuple[object, ...] = ()) -> None:
            del params
            executed.append(query.strip())

        def fetchone(self):
            return None

        def fetchall(self):
            return []

        def close(self) -> None:
            pass

    class RecordingConnection:
        def cursor(self) -> RecordingCursor:
            return RecordingCursor()

    PostgresStorageRepository(
        "postgresql://reposcan:reposcan@localhost:5432/reposcan",
        connection=RecordingConnection(),
        dialect="postgres",
    )

    assert any("CREATE EXTENSION IF NOT EXISTS postgis" in statement for statement in executed)
    assert any("CREATE TABLE IF NOT EXISTS detections" in statement for statement in executed)


def test_create_development_storage_service_uses_json_backend_by_default(tmp_path):
    service = create_development_storage_service(
        deployment_config_path=REPO_ROOT / "configs" / "deployments" / "local-dev.yaml",
        metadata_root=tmp_path / "metadata",
    )

    assert isinstance(service.repository, JsonFileStorageRepository)


def test_create_development_storage_service_selects_postgres_backend(tmp_path, monkeypatch):
    deployment_data = yaml.safe_load((REPO_ROOT / "configs" / "deployments" / "local-dev.yaml").read_text(encoding="utf-8"))
    deployment_data["infrastructure"]["metadata_backend"] = "postgres"
    deployment_path = tmp_path / "deployment-postgres.yaml"
    deployment_path.write_text(yaml.safe_dump(deployment_data, sort_keys=False), encoding="utf-8")

    created: dict[str, object] = {}

    class FakePostgresRepository:
        def __init__(self, dsn: str) -> None:
            created["dsn"] = dsn

    monkeypatch.setattr("reposcan_storage.service.PostgresStorageRepository", FakePostgresRepository)

    service = create_storage_service_from_deployment(
        deployment_config_path=deployment_path,
        metadata_root=tmp_path / "metadata",
        seed_demo_data=False,
    )

    assert created["dsn"] == "postgresql://reposcan:reposcan@localhost:5432/reposcan"
    assert type(service.repository).__name__ == "FakePostgresRepository"


def test_bootstrap_postgres_storage_rejects_non_postgres_profile():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/bootstrap_postgres_storage.py",
            "--deployment-config",
            "configs/deployments/local-dev.yaml",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "metadata_backend=postgres" in (result.stdout + result.stderr)
