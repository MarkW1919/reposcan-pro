"""FastAPI application skeleton for RepoScan Pro."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import HealthResponse, HealthState
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord
from reposcan_storage.service import (
    DetectionNotFoundError,
    HotlistNotFoundError,
    StorageService,
    create_development_storage_service,
)

from .models import HotlistSubmission, ReviewSubmission


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_app(storage_service: StorageService | None = None) -> FastAPI:
    service = storage_service or create_development_storage_service()

    app = FastAPI(
        title="RepoScan Pro API",
        version="0.1.0",
        description="Phase 4 API skeleton for local health, detections, reviews, alerts, and hotlist management.",
    )
    app.state.storage_service = service

    @app.get("/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        dependencies = service.dependency_health()
        state = HealthState.ok if all(dep.state == HealthState.ok for dep in dependencies) else HealthState.degraded
        return HealthResponse(
            service="api",
            version=app.version,
            state=state,
            timestamp_utc=_utcnow(),
            dependencies=dependencies,
        )

    @app.get("/detections", response_model=list[DetectionRecord])
    def list_detections(
        camera_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[DetectionRecord]:
        return service.list_detections(camera_id=camera_id, limit=limit)

    @app.get("/detections/{detection_id}", response_model=DetectionRecord)
    def get_detection(detection_id: str) -> DetectionRecord:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        return detection

    @app.post("/reviews/{detection_id}", response_model=ReviewRecord, status_code=status.HTTP_201_CREATED)
    def create_review(detection_id: str, submission: ReviewSubmission) -> ReviewRecord:
        review = ReviewRecord(
            review_id=f"rev_{uuid4().hex[:12]}",
            detection_id=detection_id,
            action=submission.action,
            operator_id=submission.operator_id,
            corrected_plate_text=submission.corrected_plate_text,
            notes=submission.notes,
            reviewed_at_utc=submission.reviewed_at_utc,
        )
        try:
            return service.create_review(review)
        except DetectionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc

    @app.get("/reviews/{detection_id}", response_model=list[ReviewRecord])
    def list_reviews(detection_id: str) -> list[ReviewRecord]:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        return service.list_reviews(detection_id)

    @app.get("/alerts", response_model=list[AlertRecord])
    def list_alerts(
        camera_id: str | None = Query(default=None),
        status_filter: AlertStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[AlertRecord]:
        return service.list_alerts(camera_id=camera_id, status=status_filter, limit=limit)

    @app.get("/alerts/{alert_id}", response_model=AlertRecord)
    def get_alert(alert_id: str) -> AlertRecord:
        alert = service.get_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert

    @app.get("/hotlists", response_model=list[HotlistEntry])
    def list_hotlists(
        active_only: bool = Query(default=False),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[HotlistEntry]:
        return service.list_hotlists(active_only=active_only, limit=limit)

    @app.post("/hotlists", response_model=HotlistEntry, status_code=status.HTTP_201_CREATED)
    def create_hotlist(submission: HotlistSubmission) -> HotlistEntry:
        now = _utcnow()
        entry = HotlistEntry(
            entry_id=f"hl_{uuid4().hex[:12]}",
            plate_text=submission.plate_text,
            label=submission.label,
            notes=submission.notes,
            active=submission.active,
            created_at_utc=now,
            updated_at_utc=now,
        )
        return service.create_hotlist(entry)

    @app.put("/hotlists/{entry_id}", response_model=HotlistEntry)
    def update_hotlist(entry_id: str, submission: HotlistSubmission) -> HotlistEntry:
        existing = service.get_hotlist(entry_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found")

        entry = HotlistEntry(
            entry_id=entry_id,
            plate_text=submission.plate_text,
            label=submission.label,
            notes=submission.notes,
            active=submission.active,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_utcnow(),
        )
        try:
            return service.update_hotlist(entry)
        except HotlistNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found") from exc

    return app
