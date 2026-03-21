"""In-memory repository implementation for tests and local wiring."""

from __future__ import annotations

from threading import RLock

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord


class InMemoryStorageRepository:
    def __init__(self) -> None:
        self._detections: dict[str, DetectionRecord] = {}
        self._reviews: list[ReviewRecord] = []
        self._alerts: dict[str, AlertRecord] = {}
        self._hotlists: dict[str, HotlistEntry] = {}
        self._lock = RLock()

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        with self._lock:
            detections = sorted(
                self._detections.values(),
                key=lambda record: record.timestamp_utc,
                reverse=True,
            )
        if camera_id is not None:
            detections = [record for record in detections if record.camera_id == camera_id]
        return detections[:limit]

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        with self._lock:
            return self._detections.get(detection_id)

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        with self._lock:
            self._detections[detection.detection_id] = detection
        return detection

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        with self._lock:
            self._reviews.append(review)
        return review

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        with self._lock:
            return sorted(
                [review for review in self._reviews if review.detection_id == detection_id],
                key=lambda record: record.reviewed_at_utc,
                reverse=True,
            )

    def list_alerts(
        self,
        *,
        camera_id: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        with self._lock:
            alerts = sorted(
                self._alerts.values(),
                key=lambda record: record.timestamp_utc,
                reverse=True,
            )
        if camera_id is not None:
            alerts = [record for record in alerts if record.camera_id == camera_id]
        if status is not None:
            alerts = [record for record in alerts if record.status == status]
        return alerts[:limit]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            self._alerts[alert.alert_id] = alert
        return alert

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        with self._lock:
            entries = sorted(
                self._hotlists.values(),
                key=lambda record: record.updated_at_utc,
                reverse=True,
            )
        if active_only:
            entries = [record for record in entries if record.active]
        return entries[:limit]

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        with self._lock:
            return self._hotlists.get(entry_id)

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        with self._lock:
            self._hotlists[entry.entry_id] = entry
        return entry
