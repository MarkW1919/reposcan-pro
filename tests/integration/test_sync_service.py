from __future__ import annotations

from reposcan_contracts.detection import DetectionRecord, SyncStatus
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService
from reposcan_sync import FlakySyncTransport, JsonSyncQueue, MemorySyncTransport, SyncService


def _detection() -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": "det_sync_001",
            "timestamp_utc": "2026-03-20T18:00:00Z",
            "camera_id": "cam_sync_01",
            "vehicle_bbox": {"x": 10, "y": 20, "w": 120, "h": 80},
            "image_path": "media/frames/cam_sync_01/frame_000001.jpg",
            "frame_number": 1,
        }
    )


def test_sync_service_marks_detection_synced(tmp_path):
    storage = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
    detection = storage.store_detection(_detection())
    service = SyncService(
        storage_service=storage,
        transport=MemorySyncTransport(),
        queue=JsonSyncQueue(tmp_path / "queue.json"),
    )

    service.enqueue_detection(detection.detection_id, available_at_utc="2026-03-20T18:00:00Z")
    result = service.run_once(now_utc="2026-03-20T18:00:10Z")

    updated = storage.get_detection(detection.detection_id)
    assert result.synced == 1
    assert updated is not None
    assert updated.sync_status == SyncStatus.synced
    assert updated.local_only_flag is False


def test_sync_service_retries_after_failure(tmp_path):
    storage = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
    detection = storage.store_detection(_detection())
    service = SyncService(
        storage_service=storage,
        transport=FlakySyncTransport(failures_before_success=1),
        queue=JsonSyncQueue(tmp_path / "queue.json"),
        retry_base_seconds=5,
        retry_max_seconds=60,
    )

    service.enqueue_detection(detection.detection_id, available_at_utc="2026-03-20T18:00:00Z")
    first = service.run_once(now_utc="2026-03-20T18:00:00Z")
    failed_detection = storage.get_detection(detection.detection_id)
    queued_items = service.queue.list_items()

    assert first.failed == 1
    assert failed_detection is not None
    assert failed_detection.sync_status == SyncStatus.failed
    assert len(queued_items) == 1

    second = service.run_once(now_utc=queued_items[0].available_at_utc)
    synced_detection = storage.get_detection(detection.detection_id)

    assert second.synced == 1
    assert synced_detection is not None
    assert synced_detection.sync_status == SyncStatus.synced
    assert service.queue.list_items() == []
