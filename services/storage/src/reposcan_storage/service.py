"""Storage service skeleton for local metadata and media layout management."""

from __future__ import annotations

from pathlib import Path

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import DependencyHealth, HealthState
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord
from reposcan_contracts.tracking import TrackedDetection

from .json_store import JsonFileStorageRepository
from .layout import MediaLayout, ensure_media_layout
from .repository import StorageRepository
from .dev_seed import seed_development_operator_data


class DetectionNotFoundError(KeyError):
    pass


class AlertNotFoundError(KeyError):
    pass


class HotlistNotFoundError(KeyError):
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

    def store_tracked_detection(self, tracked_detection: TrackedDetection) -> DetectionRecord:
        image_path = tracked_detection.evidence_refs.best_frame_path
        if not image_path:
            raise ValueError("tracked detection must include evidence_refs.best_frame_path")

        plate_candidates = []
        if tracked_detection.best_plate_candidate is not None:
            plate_candidates.append(tracked_detection.best_plate_candidate)
        plate_candidates.extend(tracked_detection.alternate_plate_candidates)

        vehicle_attributes = tracked_detection.vehicle_attributes
        detection = DetectionRecord(
            detection_id=tracked_detection.detection_id,
            timestamp_utc=tracked_detection.timestamp_utc,
            camera_id=tracked_detection.camera_id,
            plate_text=tracked_detection.best_plate_candidate.text if tracked_detection.best_plate_candidate else None,
            plate_confidence=(
                tracked_detection.best_plate_candidate.confidence
                if tracked_detection.best_plate_candidate is not None
                else None
            ),
            plate_candidates=plate_candidates,
            vehicle_bbox=tracked_detection.vehicle_bbox,
            plate_bbox=tracked_detection.plate_bbox,
            vehicle_color=vehicle_attributes.color if vehicle_attributes is not None else None,
            vehicle_color_confidence=vehicle_attributes.color_confidence if vehicle_attributes is not None else None,
            vehicle_make=vehicle_attributes.make if vehicle_attributes is not None else None,
            vehicle_make_confidence=vehicle_attributes.make_confidence if vehicle_attributes is not None else None,
            vehicle_model=vehicle_attributes.model_label if vehicle_attributes is not None else None,
            vehicle_model_confidence=vehicle_attributes.model_confidence if vehicle_attributes is not None else None,
            optional_vehicle_year=vehicle_attributes.year if vehicle_attributes is not None else None,
            optional_year_confidence=vehicle_attributes.year_confidence if vehicle_attributes is not None else None,
            tracker_id=tracked_detection.tracker_id,
            image_path=image_path,
            plate_crop_path=tracked_detection.evidence_refs.best_plate_crop_path,
            source_video_path=tracked_detection.evidence_refs.snippet_path,
            frame_number=tracked_detection.frame_number,
        )
        return self.store_detection(detection)

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        if self.repository.get_detection(review.detection_id) is None:
            raise DetectionNotFoundError(review.detection_id)
        return self.repository.create_review(review)

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        return self.repository.list_reviews(detection_id)

    def list_alerts(
        self,
        *,
        camera_id: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        return self.repository.list_alerts(camera_id=camera_id, status=status, limit=limit)

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        return self.repository.get_alert(alert_id)

    def store_alert(self, alert: AlertRecord) -> AlertRecord:
        return self.repository.create_alert(alert)

    def update_alert(self, alert: AlertRecord) -> AlertRecord:
        if self.repository.get_alert(alert.alert_id) is None:
            raise AlertNotFoundError(alert.alert_id)
        return self.repository.create_alert(alert)

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        return self.repository.list_hotlists(active_only=active_only, limit=limit)

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        return self.repository.get_hotlist(entry_id)

    def create_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        return self.repository.upsert_hotlist(entry)

    def update_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        if self.repository.get_hotlist(entry.entry_id) is None:
            raise HotlistNotFoundError(entry.entry_id)
        return self.repository.upsert_hotlist(entry)

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
    service = StorageService(
        repository=repository,
        media_root=deployment.infrastructure.media_root,
    )
    seed_development_operator_data(service)
    return service
