"""Storage service skeleton for local metadata and media layout management."""

from __future__ import annotations

from pathlib import Path

from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import DependencyHealth, HealthState
from reposcan_contracts.review import ReviewRecord

from .json_store import JsonFileStorageRepository
from .layout import MediaLayout, ensure_media_layout
from .repository import StorageRepository


class DetectionNotFoundError(KeyError):
    pass


class StorageService:
    def __init__(self, repository: StorageRepository, media_root: str | Path) -> None:
        self.repository = repository
        self.media_layout = ensure_media_layout(media_root)

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        return self.repository.list_detections(camera_id=camera_id, limit=limit)

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        return self.repository.get_detection(detection_id)

    def store_detection(self, detection: DetectionRecord) -> DetectionRecord:
        return self.repository.upsert_detection(detection)

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        if self.repository.get_detection(review.detection_id) is None:
            raise DetectionNotFoundError(review.detection_id)
        return self.repository.create_review(review)

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        return self.repository.list_reviews(detection_id)

    def dependency_health(self) -> list[DependencyHealth]:
        return [
            DependencyHealth(
                name="metadata-store",
                state=HealthState.ok,
                message=type(self.repository).__name__,
            ),
            DependencyHealth(
                name="media-root",
                state=HealthState.ok,
                message=str(self.media_layout.root),
            ),
        ]


def create_development_storage_service(
    *,
    deployment_config_path: str | Path = "configs/deployments/local-dev.yaml",
    metadata_root: str | Path = "runtime/storage",
) -> StorageService:
    deployment = load_deployment_config(deployment_config_path)
    repository = JsonFileStorageRepository(metadata_root)
    return StorageService(
        repository=repository,
        media_root=deployment.infrastructure.media_root,
    )
