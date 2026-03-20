"""In-memory repository implementation for tests and local wiring."""

from __future__ import annotations

from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.review import ReviewRecord


class InMemoryStorageRepository:
    def __init__(self) -> None:
        self._detections: dict[str, DetectionRecord] = {}
        self._reviews: list[ReviewRecord] = []

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        detections = sorted(
            self._detections.values(),
            key=lambda record: record.timestamp_utc,
            reverse=True,
        )
        if camera_id is not None:
            detections = [record for record in detections if record.camera_id == camera_id]
        return detections[:limit]

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        return self._detections.get(detection_id)

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        self._detections[detection.detection_id] = detection
        return detection

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        self._reviews.append(review)
        return review

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        return [review for review in self._reviews if review.detection_id == detection_id]
