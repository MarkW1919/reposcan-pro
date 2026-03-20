"""Repository interfaces for local metadata persistence."""

from __future__ import annotations

from typing import Protocol

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord


class StorageRepository(Protocol):
    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        ...

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        ...

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        ...

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        ...

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        ...

    def list_alerts(
        self,
        *,
        camera_id: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        ...

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        ...

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        ...

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        ...

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        ...

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        ...
