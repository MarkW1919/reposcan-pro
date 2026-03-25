"""Storage service skeleton for local metadata and media layout management."""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.config.deployment import (
    DeploymentConfig,
    MediaRetentionConfig,
    MetadataBackend,
    StoragePressureConfig,
)
from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import DependencyHealth, HealthState
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord
from reposcan_contracts.tracking import TrackedDetection

from .json_store import JsonFileStorageRepository
from .layout import MediaLayout, ensure_media_layout
from .postgres import PostgresStorageRepository
from .repository import StorageRepository
from .dev_seed import seed_development_operator_data


class DetectionNotFoundError(KeyError):
    pass


class AlertNotFoundError(KeyError):
    pass


class HotlistNotFoundError(KeyError):
    pass


class StorageCapacityError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(timestamp_utc: str) -> datetime:
    return datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(frozen=True)
class StoragePressureReport:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    warning_threshold_bytes: int
    minimum_threshold_bytes: int
    status: str


@dataclass(frozen=True)
class MediaRetentionSweepReport:
    reference_time_utc: str
    deleted_counts: dict[str, int] = field(default_factory=dict)
    kept_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceExportResult:
    detection_id: str
    export_path: Path
    included_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)


class StorageService:
    def __init__(
        self,
        repository: StorageRepository,
        media_root: str | Path,
        *,
        deployment_config: DeploymentConfig | None = None,
    ) -> None:
        self.repository = repository
        self.media_layout = ensure_media_layout(media_root)
        self.deployment_config = deployment_config

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

    def _retention_config(self) -> MediaRetentionConfig:
        if self.deployment_config is not None:
            return self.deployment_config.media_retention
        return MediaRetentionConfig()

    def _storage_pressure_config(self) -> StoragePressureConfig:
        if self.deployment_config is not None:
            return self.deployment_config.storage_pressure
        return StoragePressureConfig()

    def assess_storage_pressure(self) -> StoragePressureReport:
        pressure = self._storage_pressure_config()
        usage = shutil.disk_usage(self.media_layout.root)
        warning_threshold_bytes = int(pressure.warning_free_space_gb * (1024**3))
        minimum_threshold_bytes = int(pressure.minimum_free_space_gb * (1024**3))
        if usage.free < minimum_threshold_bytes:
            status = "critical"
        elif usage.free < warning_threshold_bytes:
            status = "warning"
        else:
            status = "ok"
        return StoragePressureReport(
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            warning_threshold_bytes=warning_threshold_bytes,
            minimum_threshold_bytes=minimum_threshold_bytes,
            status=status,
        )

    def sweep_media_retention(self, *, reference_time_utc: str | None = None) -> MediaRetentionSweepReport:
        retention = self._retention_config()
        reference_time = _parse_utc(reference_time_utc) if reference_time_utc is not None else datetime.now(timezone.utc)
        categories = {
            "frames": (self.media_layout.frames, retention.frames_days),
            "crops": (self.media_layout.crops, retention.crops_days),
            "snippets": (self.media_layout.snippets, retention.snippets_days),
            "exports": (self.media_layout.exports, retention.exports_days),
        }

        deleted_counts: dict[str, int] = {}
        kept_counts: dict[str, int] = {}
        for name, (root, days) in categories.items():
            cutoff = reference_time - timedelta(days=days)
            deleted = 0
            kept = 0
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if modified_at < cutoff:
                    path.unlink()
                    deleted += 1
                else:
                    kept += 1
            deleted_counts[name] = deleted
            kept_counts[name] = kept

        return MediaRetentionSweepReport(
            reference_time_utc=reference_time.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            deleted_counts=deleted_counts,
            kept_counts=kept_counts,
        )

    def _resolve_media_reference(self, media_reference: str | None) -> Path | None:
        if not media_reference:
            return None
        candidate = Path(media_reference)
        if candidate.is_absolute():
            return candidate if candidate.exists() else None

        parts = candidate.parts
        if parts and parts[0] == self.media_layout.root.name:
            relative_parts = parts[1:]
        else:
            relative_parts = parts
        relative_path = Path(*relative_parts) if relative_parts else Path()

        for base in (self.media_layout.root, self.media_layout.root.parent):
            resolved = base / relative_path
            if resolved.exists():
                return resolved
        return None

    def export_detection_package(
        self,
        detection_id: str,
        *,
        destination_path: str | Path | None = None,
    ) -> EvidenceExportResult:
        detection = self.get_detection(detection_id)
        if detection is None:
            raise DetectionNotFoundError(detection_id)

        pressure = self.assess_storage_pressure()
        if pressure.status == "critical":
            raise StorageCapacityError(
                f"storage free space below minimum threshold: {pressure.free_bytes} < {pressure.minimum_threshold_bytes}"
            )

        export_path = Path(destination_path) if destination_path is not None else self.media_layout.exports / f"{detection_id}.zip"
        export_path.parent.mkdir(parents=True, exist_ok=True)

        reviews = self.list_reviews(detection_id)
        alerts = [alert for alert in self.list_alerts(limit=10_000) if alert.detection_id == detection_id]
        hotlist_entries = [
            hotlist
            for hotlist in (
                self.get_hotlist(alert.hotlist_entry_id)
                for alert in alerts
                if alert.hotlist_entry_id is not None
            )
            if hotlist is not None
        ]

        included_files: list[str] = []
        missing_files: list[str] = []
        media_entries = [
            ("frame", detection.image_path, "evidence/frame"),
            ("plate_crop", detection.plate_crop_path, "evidence/crop"),
            ("snippet", detection.source_video_path, "evidence/snippet"),
        ]
        manifest = {
            "exported_at_utc": _utcnow(),
            "detection": detection.model_dump(mode="json"),
            "reviews": [review.model_dump(mode="json") for review in reviews],
            "alerts": [alert.model_dump(mode="json") for alert in alerts],
            "hotlists": [entry.model_dump(mode="json") for entry in hotlist_entries],
            "storage_pressure": {
                "status": pressure.status,
                "free_bytes": pressure.free_bytes,
                "warning_threshold_bytes": pressure.warning_threshold_bytes,
                "minimum_threshold_bytes": pressure.minimum_threshold_bytes,
            },
            "included_files": included_files,
            "missing_files": missing_files,
        }

        with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for label, reference, export_prefix in media_entries:
                resolved_path = self._resolve_media_reference(reference)
                if resolved_path is None:
                    if reference:
                        missing_files.append(label)
                    continue
                archive_name = f"{export_prefix}/{resolved_path.name}"
                archive.write(resolved_path, arcname=archive_name)
                included_files.append(archive_name)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))

        return EvidenceExportResult(
            detection_id=detection_id,
            export_path=export_path,
            included_files=included_files,
            missing_files=missing_files,
        )

    def dependency_health(self) -> list[DependencyHealth]:
        pressure = self.assess_storage_pressure()
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
            DependencyHealth(
                name="storage-pressure",
                state=(
                    HealthState.ok
                    if pressure.status == "ok"
                    else HealthState.warning
                    if pressure.status == "warning"
                    else HealthState.error
                ),
                message=f"{pressure.status}: {pressure.free_bytes} bytes free",
            ),
        ]


def create_storage_service_from_deployment(
    *,
    deployment_config_path: str | Path = "configs/deployments/local-dev.yaml",
    metadata_root: str | Path = "runtime/storage",
    seed_demo_data: bool = False,
) -> StorageService:
    deployment = load_deployment_config(deployment_config_path)
    if deployment.infrastructure.metadata_backend == MetadataBackend.postgres:
        repository = PostgresStorageRepository(deployment.infrastructure.postgres_url)
    else:
        repository = JsonFileStorageRepository(metadata_root)
    service = StorageService(
        repository=repository,
        media_root=deployment.infrastructure.media_root,
        deployment_config=deployment,
    )
    if seed_demo_data:
        seed_development_operator_data(service)
    return service


def create_development_storage_service(
    *,
    deployment_config_path: str | Path = "configs/deployments/local-dev.yaml",
    metadata_root: str | Path = "runtime/storage",
) -> StorageService:
    service = create_storage_service_from_deployment(
        deployment_config_path=deployment_config_path,
        metadata_root=metadata_root,
        seed_demo_data=True,
    )
    return service
