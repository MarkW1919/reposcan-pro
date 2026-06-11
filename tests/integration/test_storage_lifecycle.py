from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from shutil import _ntuple_diskusage

import pytest

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord
from reposcan_storage.json_store import JsonFileStorageRepository
from reposcan_storage.service import StorageCapacityError, StorageService


REPO_ROOT = Path(__file__).resolve().parents[2]


def _detection_record() -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": "det_export_001",
            "timestamp_utc": "2026-03-24T20:00:00Z",
            "camera_id": "cam_export_01",
            "plate_text": "8ABC123",
            "plate_confidence": 0.93,
            "plate_candidates": [{"text": "8ABC123", "confidence": 0.93}],
            "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
            "plate_bbox": {"x": 518, "y": 338, "w": 86, "h": 28},
            "vehicle_color": "white",
            "vehicle_color_confidence": 0.88,
            "vehicle_make": "toyota",
            "vehicle_make_confidence": 0.67,
            "vehicle_model": "camry",
            "vehicle_model_confidence": 0.54,
            "tracker_id": "trk_export_001",
            "image_path": "media/frames/cam_export_01/frame_000001.jpg",
            "plate_crop_path": "media/crops/cam_export_01/plate_000001.jpg",
            "source_video_path": "media/snippets/cam_export_01/snippet_000001.mp4",
            "frame_number": 1,
        }
    )


def _review_record() -> ReviewRecord:
    return ReviewRecord.model_validate(
        {
            "review_id": "rev_export_001",
            "detection_id": "det_export_001",
            "action": "confirm",
            "reviewed_at_utc": "2026-03-24T20:01:00Z",
        }
    )


def _hotlist_entry() -> HotlistEntry:
    return HotlistEntry.model_validate(
        {
            "entry_id": "hl_export_001",
            "plate_text": "8ABC123",
            "label": "Export case",
            "created_at_utc": "2026-03-24T19:59:00Z",
            "updated_at_utc": "2026-03-24T19:59:00Z",
        }
    )


def _alert_record() -> AlertRecord:
    return AlertRecord.model_validate(
        {
            "alert_id": "alert_export_001",
            "detection_id": "det_export_001",
            "hotlist_entry_id": "hl_export_001",
            "timestamp_utc": "2026-03-24T20:02:00Z",
            "camera_id": "cam_export_01",
            "matched_plate_text": "8ABC123",
            "match_confidence": 0.92,
            "match_type": "exact",
            "hotlist_label": "Export case",
        }
    )


def _deployment():
    deployment = load_deployment_config(REPO_ROOT / "configs" / "deployments" / "local-dev.yaml")
    deployment = deployment.model_copy(deep=True)
    deployment.media_retention.frames_days = 1
    deployment.media_retention.crops_days = 1
    deployment.media_retention.snippets_days = 1
    deployment.media_retention.exports_days = 1
    deployment.storage_pressure.warning_free_space_gb = 0.01
    deployment.storage_pressure.minimum_free_space_gb = 0.005
    return deployment


def _storage_service(tmp_path: Path) -> StorageService:
    return StorageService(
        repository=JsonFileStorageRepository(tmp_path / "metadata"),
        media_root=tmp_path / "media",
        deployment_config=_deployment(),
    )


def _touch_media_file(path: Path, *, age_days: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture")
    base_epoch = datetime(2024, 3, 24, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    age_seconds = age_days * 24 * 60 * 60
    os.utime(path, (base_epoch - age_seconds, base_epoch - age_seconds))


def _seed_export_files(media_root: Path) -> None:
    (media_root / "frames" / "cam_export_01").mkdir(parents=True, exist_ok=True)
    (media_root / "crops" / "cam_export_01").mkdir(parents=True, exist_ok=True)
    (media_root / "snippets" / "cam_export_01").mkdir(parents=True, exist_ok=True)
    (media_root / "frames" / "cam_export_01" / "frame_000001.jpg").write_bytes(b"frame")
    (media_root / "crops" / "cam_export_01" / "plate_000001.jpg").write_bytes(b"crop")
    (media_root / "snippets" / "cam_export_01" / "snippet_000001.mp4").write_bytes(b"snippet")


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_json_repository_recovers_from_backup_after_corruption(tmp_path):
    repository = JsonFileStorageRepository(tmp_path / "metadata")
    detection = _detection_record()
    repository.upsert_detection(detection)

    detections_path = tmp_path / "metadata" / "detections.json"
    detections_path.write_text("{broken json", encoding="utf-8")

    recovered = JsonFileStorageRepository(tmp_path / "metadata")

    assert recovered.get_detection(detection.detection_id) == detection


def test_storage_service_sweeps_media_retention(tmp_path):
    service = _storage_service(tmp_path)
    old_frame = service.media_layout.frames / "cam_export_01" / "old_frame.jpg"
    old_crop = service.media_layout.crops / "cam_export_01" / "old_crop.jpg"
    recent_frame = service.media_layout.frames / "cam_export_01" / "recent_frame.jpg"

    _touch_media_file(old_frame, age_days=3)
    _touch_media_file(old_crop, age_days=2)
    _touch_media_file(recent_frame, age_days=0)

    report = service.sweep_media_retention(reference_time_utc="2024-03-24T00:00:00Z")

    assert report.deleted_counts["frames"] == 1
    assert report.deleted_counts["crops"] == 1
    assert report.kept_counts["frames"] == 1
    assert not old_frame.exists()
    assert not old_crop.exists()
    assert recent_frame.exists()


def test_export_detection_package_writes_manifest_and_media(tmp_path):
    service = _storage_service(tmp_path)
    _seed_export_files(service.media_layout.root)
    detection = _detection_record()

    service.store_detection(detection)
    service.create_review(_review_record())
    service.create_hotlist(_hotlist_entry())
    service.store_alert(_alert_record())

    export_result = service.export_detection_package(detection.detection_id)

    assert export_result.export_path.exists()
    assert not export_result.missing_files

    with zipfile.ZipFile(export_result.export_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "evidence/frame/frame_000001.jpg" in names
        assert "evidence/crop/plate_000001.jpg" in names
        assert "evidence/snippet/snippet_000001.mp4" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["detection"]["detection_id"] == detection.detection_id
    assert len(manifest["reviews"]) == 1
    assert len(manifest["alerts"]) == 1
    assert len(manifest["hotlists"]) == 1


def test_export_detection_package_blocks_on_critical_storage_pressure(tmp_path, monkeypatch):
    service = _storage_service(tmp_path)
    _seed_export_files(service.media_layout.root)
    detection = _detection_record()
    service.store_detection(detection)

    monkeypatch.setattr(
        "reposcan_storage.service.shutil.disk_usage",
        lambda _path: _ntuple_diskusage(total=10_000_000_000, used=9_999_000_000, free=1_000_000),
    )

    with pytest.raises(StorageCapacityError):
        service.export_detection_package(detection.detection_id)


def test_export_detection_package_script_writes_zip(tmp_path):
    service = _storage_service(tmp_path)
    _seed_export_files(service.media_layout.root)
    detection = _detection_record()
    service.store_detection(detection)
    service.create_review(_review_record())
    service.create_hotlist(_hotlist_entry())
    service.store_alert(_alert_record())

    output_path = tmp_path / "exports" / "det_export_001.zip"
    result = _run_script(
        "scripts/export_detection_package.py",
        "--detection-id",
        detection.detection_id,
        "--deployment-config",
        "configs/deployments/local-dev.yaml",
        "--metadata-root",
        str(tmp_path / "metadata"),
        "--media-root",
        str(tmp_path / "media"),
        "--output-path",
        str(output_path),
        "--json",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["export_path"]).exists()
    assert "evidence/frame/frame_000001.jpg" in payload["included_files"]


def test_run_storage_maintenance_script_reports_pressure_and_retention(tmp_path):
    service = _storage_service(tmp_path)
    old_frame = service.media_layout.frames / "cam_export_01" / "old_frame.jpg"
    _touch_media_file(old_frame, age_days=10)

    result = _run_script(
        "scripts/run_storage_maintenance.py",
        "--deployment-config",
        "configs/deployments/local-dev.yaml",
        "--metadata-root",
        str(tmp_path / "metadata"),
        "--media-root",
        str(tmp_path / "media"),
        "--reference-time-utc",
        "2024-03-24T00:00:00Z",
        "--json",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["storage_pressure"]["status"] == "ok"
    assert payload["retention"]["deleted_counts"]["frames"] == 1
