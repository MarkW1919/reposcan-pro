"""Optional remote sync service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord, SyncStatus
from reposcan_storage.service import StorageService, create_development_storage_service

from .models import SyncQueueItem, SyncRunResult
from .queue import JsonSyncQueue
from .transports import MemorySyncTransport, SyncTransport


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(timestamp_utc: str) -> datetime:
    return datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class SyncService:
    def __init__(
        self,
        *,
        storage_service: StorageService,
        transport: SyncTransport,
        queue: JsonSyncQueue,
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 300,
    ) -> None:
        self.storage_service = storage_service
        self.transport = transport
        self.queue = queue
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    def enqueue_detection(self, detection_id: str, *, available_at_utc: str | None = None) -> SyncQueueItem:
        detection = self.storage_service.get_detection(detection_id)
        if detection is None:
            raise KeyError(f"Unknown detection '{detection_id}'")

        existing = self.queue.get_by_record(record_type="detection", record_id=detection_id)
        if existing is not None:
            return existing

        return self.queue.upsert(
            SyncQueueItem(
                queue_id=f"sync_{uuid4().hex[:12]}",
                record_type="detection",
                record_id=detection_id,
                available_at_utc=available_at_utc or _utcnow(),
            )
        )

    def enqueue_unsynced_detections(self, *, limit: int = 100) -> list[SyncQueueItem]:
        queued: list[SyncQueueItem] = []
        detections = self.storage_service.list_detections(limit=limit)
        for detection in detections:
            if detection.sync_status == SyncStatus.synced:
                continue
            queued.append(self.enqueue_detection(detection.detection_id))
        return queued

    def run_once(self, *, now_utc: str | None = None, limit: int = 100) -> SyncRunResult:
        now = _parse_utc(now_utc or _utcnow())
        result = SyncRunResult()
        processed = 0

        for item in self.queue.list_items():
            if processed >= limit:
                break
            if _parse_utc(item.available_at_utc) > now:
                continue
            processed += 1

            if item.record_type != "detection":
                self.queue.remove(item.queue_id)
                result.skipped += 1
                continue

            detection = self.storage_service.get_detection(item.record_id)
            if detection is None:
                self.queue.remove(item.queue_id)
                result.skipped += 1
                continue

            try:
                self.transport.send_detection(detection)
            except Exception as exc:
                failed_detection = detection.model_copy(
                    update={
                        "sync_status": SyncStatus.failed,
                        "local_only_flag": True,
                    }
                )
                self.storage_service.store_detection(failed_detection)
                retry_at = now + timedelta(seconds=min(self.retry_base_seconds * (2 ** item.attempts), self.retry_max_seconds))
                self.queue.upsert(
                    item.model_copy(
                        update={
                            "attempts": item.attempts + 1,
                            "available_at_utc": _format_utc(retry_at),
                            "last_error": str(exc),
                        }
                    )
                )
                result.failed += 1
                continue

            synced_detection = detection.model_copy(
                update={
                    "sync_status": SyncStatus.synced,
                    "local_only_flag": False,
                }
            )
            self.storage_service.store_detection(synced_detection)
            self.queue.remove(item.queue_id)
            result.synced += 1

        return result


def create_development_sync_service(
    *,
    deployment_config_path: str | Path = "configs/deployments/local-dev.yaml",
    queue_path: str | Path = "runtime/sync/detection_queue.json",
    storage_service: StorageService | None = None,
    transport: SyncTransport | None = None,
) -> SyncService:
    deployment = load_deployment_config(deployment_config_path)
    queue = JsonSyncQueue(queue_path)
    return SyncService(
        storage_service=storage_service or create_development_storage_service(deployment_config_path=deployment_config_path),
        transport=transport or MemorySyncTransport(),
        queue=queue,
        retry_base_seconds=5 if deployment.target_hardware.value == "cpu" else 3,
        retry_max_seconds=300,
    )
