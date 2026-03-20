"""JSON-backed repository for the Phase 2 storage skeleton.

This keeps the persistence surface local-first and file-backed while the later
Postgres adapter is introduced. The repository contract is intentionally small
so it can be replaced without disturbing API handlers.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import TypeVar

from pydantic import BaseModel

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord

ModelT = TypeVar("ModelT", bound=BaseModel)


class JsonFileStorageRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._detections_path = self.root / "detections.json"
        self._reviews_path = self.root / "reviews.json"
        self._alerts_path = self.root / "alerts.json"
        self._hotlists_path = self.root / "hotlists.json"
        self._lock = RLock()
        self._ensure_file(self._detections_path)
        self._ensure_file(self._reviews_path)
        self._ensure_file(self._alerts_path)
        self._ensure_file(self._hotlists_path)

    def _ensure_file(self, path: Path) -> None:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")

    def _read_records(self, path: Path, model_type: type[ModelT]) -> list[ModelT]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model_type.model_validate(item) for item in payload]

    def _write_records(self, path: Path, records: list[BaseModel]) -> None:
        payload = [record.model_dump(mode="json") for record in records]
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        with self._lock:
            detections = self._read_records(self._detections_path, DetectionRecord)
        detections = sorted(detections, key=lambda record: record.timestamp_utc, reverse=True)
        if camera_id is not None:
            detections = [record for record in detections if record.camera_id == camera_id]
        return detections[:limit]

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        with self._lock:
            detections = self._read_records(self._detections_path, DetectionRecord)
        for detection in detections:
            if detection.detection_id == detection_id:
                return detection
        return None

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        with self._lock:
            detections = self._read_records(self._detections_path, DetectionRecord)
            by_id = {record.detection_id: record for record in detections}
            by_id[detection.detection_id] = detection
            ordered = sorted(by_id.values(), key=lambda record: record.timestamp_utc, reverse=True)
            self._write_records(self._detections_path, ordered)
        return detection

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        with self._lock:
            reviews = self._read_records(self._reviews_path, ReviewRecord)
            reviews.append(review)
            self._write_records(self._reviews_path, reviews)
        return review

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        with self._lock:
            reviews = self._read_records(self._reviews_path, ReviewRecord)
        return sorted(
            [review for review in reviews if review.detection_id == detection_id],
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
            alerts = self._read_records(self._alerts_path, AlertRecord)
        alerts = sorted(alerts, key=lambda record: record.timestamp_utc, reverse=True)
        if camera_id is not None:
            alerts = [record for record in alerts if record.camera_id == camera_id]
        if status is not None:
            alerts = [record for record in alerts if record.status == status]
        return alerts[:limit]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            alerts = self._read_records(self._alerts_path, AlertRecord)
        for alert in alerts:
            if alert.alert_id == alert_id:
                return alert
        return None

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            alerts = self._read_records(self._alerts_path, AlertRecord)
            by_id = {record.alert_id: record for record in alerts}
            by_id[alert.alert_id] = alert
            ordered = sorted(by_id.values(), key=lambda record: record.timestamp_utc, reverse=True)
            self._write_records(self._alerts_path, ordered)
        return alert

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
        entries = sorted(entries, key=lambda record: record.updated_at_utc, reverse=True)
        if active_only:
            entries = [record for record in entries if record.active]
        return entries[:limit]

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
            by_id = {record.entry_id: record for record in entries}
            by_id[entry.entry_id] = entry
            ordered = sorted(by_id.values(), key=lambda record: record.updated_at_utc, reverse=True)
            self._write_records(self._hotlists_path, ordered)
        return entry
