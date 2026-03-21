"""FastAPI application skeleton for RepoScan Pro."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import HealthResponse, HealthState
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.popup import PopupActivityEvent, PopupEventType
from reposcan_contracts.review import ReviewRecord
from reposcan_inference import DemoRunInProgressError, DemoRunStatus as RuntimeDemoRunStatus, HeadlessDemoRunManager
from reposcan_storage.service import (
    DetectionNotFoundError,
    HotlistNotFoundError,
    StorageService,
    create_development_storage_service,
)

from .models import (
    DashboardCounts,
    DashboardOverview,
    DemoRunSubmission,
    DemoRunSummary,
    DemoRuntimeStatus,
    HotlistSubmission,
    ReviewSubmission,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _best_detection_confidence(detection: DetectionRecord) -> float:
    if detection.plate_confidence is not None:
        return detection.plate_confidence
    if detection.plate_candidates:
        return max(candidate.confidence for candidate in detection.plate_candidates)
    return 0.0


def _build_address_popup_note(detection: DetectionRecord) -> str:
    if detection.plate_text:
        return "General detection is ready to surface when active scan mode is enabled."
    return "Vehicle detection is available, but the best plate read is still pending or occluded."


def _build_popup_activity(
    *,
    detections: list[DetectionRecord],
    alerts: list[AlertRecord],
    limit: int,
) -> list[PopupActivityEvent]:
    detections_by_id = {record.detection_id: record for record in detections}
    alert_detection_ids: set[str] = set()
    events: list[PopupActivityEvent] = []

    for alert in alerts:
        detection = detections_by_id.get(alert.detection_id)
        events.append(
            PopupActivityEvent(
                event_id=f"popup_{alert.alert_id}",
                event_type=PopupEventType.hotlist,
                source_record_id=alert.alert_id,
                detection_id=alert.detection_id,
                timestamp_utc=alert.timestamp_utc,
                camera_id=alert.camera_id,
                plate_text=alert.matched_plate_text,
                confidence=alert.match_confidence,
                vehicle_color=detection.vehicle_color if detection is not None else None,
                vehicle_make=detection.vehicle_make if detection is not None else None,
                vehicle_model=detection.vehicle_model if detection is not None else None,
                optional_vehicle_year=detection.optional_vehicle_year if detection is not None else None,
                hotlist_label=alert.hotlist_label,
                gps_latitude=alert.gps_latitude if alert.gps_latitude is not None else detection.gps_latitude if detection is not None else None,
                gps_longitude=alert.gps_longitude if alert.gps_longitude is not None else detection.gps_longitude if detection is not None else None,
                note=alert.notes,
            )
        )
        alert_detection_ids.add(alert.detection_id)

    for detection in detections:
        if detection.detection_id in alert_detection_ids:
            continue

        events.append(
            PopupActivityEvent(
                event_id=f"popup_{detection.detection_id}",
                event_type=PopupEventType.address,
                source_record_id=detection.detection_id,
                detection_id=detection.detection_id,
                timestamp_utc=detection.timestamp_utc,
                camera_id=detection.camera_id,
                plate_text=detection.plate_text,
                confidence=_best_detection_confidence(detection),
                vehicle_color=detection.vehicle_color,
                vehicle_make=detection.vehicle_make,
                vehicle_model=detection.vehicle_model,
                optional_vehicle_year=detection.optional_vehicle_year,
                gps_latitude=detection.gps_latitude,
                gps_longitude=detection.gps_longitude,
                note=_build_address_popup_note(detection),
            )
        )

    events.sort(key=lambda event: event.timestamp_utc, reverse=True)
    return events[:limit]


def _build_demo_runtime_status(status: RuntimeDemoRunStatus) -> DemoRuntimeStatus:
    summary = None
    if status.summary is not None:
        summary = DemoRunSummary(
            frames_captured=status.summary.frames_captured,
            candidates_processed=status.summary.candidates_processed,
            tracks_finalized=status.summary.tracks_finalized,
            stored_detection_ids=status.summary.stored_detection_ids,
            created_alert_ids=status.summary.created_alert_ids,
        )

    return DemoRuntimeStatus(
        state=status.state,
        run_id=status.run_id,
        started_at_utc=status.started_at_utc,
        completed_at_utc=status.completed_at_utc,
        frames_directory=status.frames_directory,
        glob_pattern=status.glob_pattern,
        sequence_id=status.sequence_id,
        plate_text=status.plate_text,
        error_message=status.error_message,
        summary=summary,
    )


def create_app(
    storage_service: StorageService | None = None,
    demo_run_manager: HeadlessDemoRunManager | None = None,
) -> FastAPI:
    service = storage_service or create_development_storage_service()
    demo_manager = demo_run_manager or HeadlessDemoRunManager(storage_service=service)

    app = FastAPI(
        title="RepoScan Pro API",
        version="0.1.0",
        description="Edge-first API for health, detections, reviews, alerts, hotlists, and dashboard overview.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.storage_service = service
    app.state.demo_run_manager = demo_manager

    def build_health_response() -> HealthResponse:
        dependencies = service.dependency_health()
        state = HealthState.ok if all(dep.state == HealthState.ok for dep in dependencies) else HealthState.degraded
        return HealthResponse(
            service="api",
            version=app.version,
            state=state,
            timestamp_utc=_utcnow(),
            dependencies=dependencies,
        )

    @app.get("/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        return build_health_response()

    @app.get("/dashboard/overview", response_model=DashboardOverview)
    def get_dashboard_overview(limit: int = Query(default=20, ge=1, le=100)) -> DashboardOverview:
        detections = service.list_detections(limit=limit)
        alerts = service.list_alerts(limit=limit)
        hotlists = service.list_hotlists(limit=limit)
        active_alerts = service.list_alerts(status=AlertStatus.active, limit=500)
        active_hotlists = service.list_hotlists(active_only=True, limit=500)
        popup_activity = _build_popup_activity(detections=detections, alerts=alerts, limit=limit)
        return DashboardOverview(
            generated_at_utc=_utcnow(),
            health=build_health_response(),
            counts=DashboardCounts(
                active_alerts=len(active_alerts),
                recent_detections=len(detections),
                active_hotlists=len(active_hotlists),
            ),
            detections=detections,
            alerts=alerts,
            hotlists=hotlists,
            popup_activity=popup_activity,
        )

    @app.get("/demo/runtime", response_model=DemoRuntimeStatus)
    def get_demo_runtime_status() -> DemoRuntimeStatus:
        return _build_demo_runtime_status(demo_manager.status())

    @app.post("/demo/runs", response_model=DemoRuntimeStatus, status_code=status.HTTP_202_ACCEPTED)
    def start_demo_run(submission: DemoRunSubmission) -> DemoRuntimeStatus:
        try:
            run_status = demo_manager.start_run(
                frames_directory=submission.frames_directory,
                start_timestamp_utc=submission.start_timestamp_utc,
                frame_interval_ms=submission.frame_interval_ms,
                glob_pattern=submission.glob_pattern,
                start_frame_number=submission.start_frame_number,
                sequence_id=submission.sequence_id,
                plate_text=submission.plate_text,
            )
        except DemoRunInProgressError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return _build_demo_runtime_status(run_status)

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
