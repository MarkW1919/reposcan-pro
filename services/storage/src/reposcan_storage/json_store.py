"""JSON-backed repository for the Phase 2 storage skeleton.

This keeps the persistence surface local-first and file-backed while the later
Postgres adapter is introduced. The repository contract is intentionally small
so it can be replaced without disturbing API handlers.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.review import ReviewRecord


class JsonFileStorageRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._detections_path = self.root / "detections.json"
        self._reviews_path = self.root / "reviews.json"
        self._lock = RLock()
        self._ensure_file(self._detections_path)
        self._ensure_file(self._reviews_path)

    def _ensure_file(self, path: Path) -> None:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")

    def _read_records(self, path: Path, model_type: type[DetectionRecord] | type[ReviewRecord]) -> list[DetectionRecord] | list[ReviewRecord]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model_type.model_validate(item) for item in payload]

    def _write_records(self, path: Path, records: list[DetectionRecord] | list[ReviewRecord]) -> None:
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
        return [review for review in reviews if review.detection_id == detection_id]
