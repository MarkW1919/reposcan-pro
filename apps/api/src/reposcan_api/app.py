"""FastAPI application skeleton for RepoScan Pro."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status

from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import HealthResponse, HealthState
from reposcan_contracts.review import ReviewRecord
from reposcan_storage.service import DetectionNotFoundError, StorageService, create_development_storage_service

from .models import ReviewSubmission


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_app(storage_service: StorageService | None = None) -> FastAPI:
    service = storage_service or create_development_storage_service()

    app = FastAPI(
        title="RepoScan Pro API",
        version="0.1.0",
        description="Phase 2 API skeleton for local health, detection retrieval, and review writes.",
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

    return app
