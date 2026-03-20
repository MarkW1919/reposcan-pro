"""Repository interfaces for local metadata persistence."""

from __future__ import annotations

from typing import Protocol

from reposcan_contracts.detection import DetectionRecord
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
