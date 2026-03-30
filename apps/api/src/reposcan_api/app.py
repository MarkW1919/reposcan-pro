"""FastAPI application skeleton for RepoScan Pro."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.config.deployment import ApiRole, DeploymentConfig
from reposcan_contracts.dispatch import DispatchAssignmentRecord, DispatchAssignmentStatus
from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord, FollowUpStatus
from reposcan_contracts.health import HealthResponse, HealthState
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorCapabilities, OperatorPrincipal, OperatorSessionRecord
from reposcan_contracts.popup import PopupActivityEvent, PopupEventType
from reposcan_contracts.review import ReviewRecord
from reposcan_inference import DemoRunInProgressError, DemoRunStatus as RuntimeDemoRunStatus, HeadlessDemoRunManager
from reposcan_storage.service import (
    AssignmentNotFoundError,
    AlertNotFoundError,
    DetectionNotFoundError,
    FollowUpNotFoundError,
    HotlistNotFoundError,
    StorageService,
    create_development_storage_service,
)

from .models import (
    AlertUpdateSubmission,
    AlertSearchResponse,
    ApiAuditEvent,
    ApiVersionInfo,
    AuditEventResponse,
    AuditOutcome,
    DashboardCounts,
    DashboardOverview,
    DetectionSearchResponse,
    DispatchAssignmentSubmission,
    DemoRunSubmission,
    DemoRunSummary,
    DemoRuntimeStatus,
    FollowUpSubmission,
    HotlistSubmission,
    OperatorSessionHeartbeatSubmission,
    ReviewSubmission,
    SearchPageInfo,
    SearchPlateMatchMode,
)
from .audit import ApiAuditLogger
from .security import ApiAccessController, ApiPrincipalContext, principal_details

_DASHBOARD_SUPPORTING_RECORD_LIMIT = 200


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


def _build_alert_popup_note(alert: AlertRecord) -> str | None:
    parts = [alert.notes, alert.response_notes]
    note = " | ".join(part for part in parts if part)
    return note or None


def _resolve_media_path(media_ref: str | None, media_root: Path) -> Path | None:
    if not media_ref:
        return None

    candidate = Path(media_ref)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None

    resolved = candidate.resolve(strict=False)
    if resolved.is_file():
        return resolved

    rooted_base = media_root.parent if candidate.parts and candidate.parts[0] == media_root.name else media_root
    rooted = (rooted_base / candidate).resolve(strict=False)
    if rooted.is_file():
        return rooted

    return None


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
        alert_detection_ids.add(alert.detection_id)
        if alert.status == AlertStatus.dismissed:
            continue
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
                note=_build_alert_popup_note(alert),
            )
        )

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


def _build_operator_capabilities(principal: ApiPrincipalContext) -> OperatorCapabilities:
    roles = set(principal.roles)
    can_operate = ApiRole.operator in roles or ApiRole.admin in roles
    return OperatorCapabilities(
        can_submit_reviews=can_operate,
        can_update_alerts=can_operate,
        can_manage_hotlists=ApiRole.admin in roles,
        can_manage_follow_ups=can_operate,
        can_manage_dispatch=can_operate,
        can_start_demo_runs=can_operate,
        can_view_audit=ApiRole.admin in roles or ApiRole.integrator in roles,
    )


def _build_operator_principal(principal: ApiPrincipalContext) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=principal.principal_id,
        display_name=principal.display_name,
        authenticated=principal.authenticated,
        roles=list(principal.roles),
        capabilities=_build_operator_capabilities(principal),
    )


def create_app(
    storage_service: StorageService | None = None,
    demo_run_manager: HeadlessDemoRunManager | None = None,
    deployment_config: DeploymentConfig | None = None,
) -> FastAPI:
    service = storage_service or create_development_storage_service()
    deployment = deployment_config or service.deployment_config or load_deployment_config("configs/deployments/local-dev.yaml")
    demo_manager = demo_run_manager or HeadlessDemoRunManager(storage_service=service)
    audit_logger = ApiAuditLogger(
        deployment.api.audit.log_root,
        enabled=deployment.api.audit.enabled,
        max_read_limit=deployment.api.audit.max_read_limit,
    )
    access_controller = ApiAccessController(deployment.api, audit_logger=audit_logger)

    app = FastAPI(
        title="RepoScan Pro API",
        version="0.1.0",
        description="Edge-first API for health, detections, alerts, reviews, hotlists, search, audit, and dashboard overview.",
        docs_url="/docs" if deployment.api.hardening.expose_docs else None,
        redoc_url="/redoc" if deployment.api.hardening.expose_docs else None,
        openapi_url="/openapi.json" if deployment.api.hardening.expose_docs else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=deployment.api.hardening.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=deployment.api.hardening.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.storage_service = service
    app.state.demo_run_manager = demo_manager
    app.state.deployment_config = deployment
    app.state.audit_logger = audit_logger
    app.state.access_controller = access_controller

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid4().hex[:12]}"
        request.state.request_id = request_id
        request.state.utcnow = _utcnow
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error", "request_id": request_id},
            )
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Api-Version"] = deployment.api.versioning.current_version
        if deployment.api.hardening.add_security_headers:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
        rate_limit_limit = getattr(request.state, "rate_limit_limit", None)
        rate_limit_remaining = getattr(request.state, "rate_limit_remaining", None)
        if rate_limit_limit is not None and rate_limit_remaining is not None:
            response.headers["X-RateLimit-Limit"] = str(rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_remaining)
        return response

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

    def build_version_info() -> ApiVersionInfo:
        return ApiVersionInfo(
            service="api",
            package_version=app.version,
            api_version=deployment.api.versioning.current_version,
            canonical_prefix=deployment.api.versioning.canonical_prefix,
            legacy_routes_enabled=deployment.api.versioning.enable_legacy_routes,
            auth_enabled=deployment.api.security.enabled,
            rate_limit_enabled=deployment.api.rate_limit.enabled,
        )

    def record_audit(
        request: Request,
        *,
        principal: ApiPrincipalContext | None,
        action: str,
        outcome: AuditOutcome,
        target_type: str | None = None,
        target_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        if not deployment.api.audit.enabled:
            return
        principal_id, principal_roles = principal_details(principal)
        audit_logger.record(
            ApiAuditEvent(
                event_id=f"audit_{uuid4().hex[:12]}",
                occurred_at_utc=_utcnow(),
                request_id=request.state.request_id,
                principal_id=principal_id,
                principal_roles=principal_roles,
                action=action,
                outcome=outcome,
                method=request.method,
                path=request.url.path,
                target_type=target_type,
                target_id=target_id,
                details=details or {},
            )
        )

    api_router = APIRouter()

    @api_router.get("/health", response_model=HealthResponse)
    def get_health(_principal: ApiPrincipalContext = Depends(access_controller.health_access)) -> HealthResponse:
        return build_health_response()

    @api_router.get("/version", response_model=ApiVersionInfo)
    def get_version_info(_principal: ApiPrincipalContext = Depends(access_controller.version_access)) -> ApiVersionInfo:
        return build_version_info()

    @api_router.get("/dashboard/overview", response_model=DashboardOverview)
    def get_dashboard_overview(
        limit: int = Query(default=20, ge=1, le=100),
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DashboardOverview:
        supporting_limit = max(limit, _DASHBOARD_SUPPORTING_RECORD_LIMIT)
        detections = service.list_detections(limit=limit)
        alerts = service.list_alerts(limit=limit)
        follow_ups = service.list_follow_ups(limit=supporting_limit)
        assignments = service.list_assignments(limit=supporting_limit)
        hotlists = service.list_hotlists(limit=supporting_limit)
        active_alerts = service.list_alerts(status=AlertStatus.active, limit=500)
        active_sessions = service.list_operator_sessions(limit=100)
        popup_activity = _build_popup_activity(detections=detections, alerts=alerts, limit=limit)
        return DashboardOverview(
            generated_at_utc=_utcnow(),
            health=build_health_response(),
            counts=DashboardCounts(
                active_alerts=len(active_alerts),
                recent_detections=len(detections),
                active_hotlists=len([record for record in hotlists if record.active]),
                open_follow_ups=len([record for record in follow_ups if record.status != FollowUpStatus.resolved]),
                active_assignments=len(
                    [
                        record
                        for record in assignments
                        if record.status not in {DispatchAssignmentStatus.completed, DispatchAssignmentStatus.cancelled}
                    ]
                ),
                active_sessions=len(active_sessions),
            ),
            detections=detections,
            alerts=alerts,
            follow_ups=follow_ups,
            assignments=assignments,
            hotlists=hotlists,
            popup_activity=popup_activity,
            current_principal=_build_operator_principal(principal),
            active_sessions=active_sessions,
        )

    @api_router.post("/operator/sessions/heartbeat", response_model=OperatorSessionRecord)
    def heartbeat_operator_session(
        submission: OperatorSessionHeartbeatSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> OperatorSessionRecord:
        session = OperatorSessionRecord(
            session_id=submission.session_id,
            principal_id=principal.principal_id,
            display_name=principal.display_name,
            authenticated=principal.authenticated,
            roles=list(principal.roles),
            client_label=submission.client_label,
            workspace=submission.workspace,
            selected_detection_id=submission.selected_detection_id,
            selected_alert_id=submission.selected_alert_id,
            navigation_active=submission.navigation_active,
            last_seen_at_utc=_utcnow(),
        )
        return service.touch_operator_session(session)

    @api_router.get("/search/detections", response_model=DetectionSearchResponse)
    def search_detections(
        request: Request,
        plate: str | None = Query(default=None),
        plate_match: SearchPlateMatchMode = Query(default=SearchPlateMatchMode.contains),
        start_utc: str | None = Query(default=None),
        end_utc: str | None = Query(default=None),
        camera_id: str | None = Query(default=None),
        min_latitude: float | None = Query(default=None),
        max_latitude: float | None = Query(default=None),
        min_longitude: float | None = Query(default=None),
        max_longitude: float | None = Query(default=None),
        vehicle_color: str | None = Query(default=None),
        vehicle_make: str | None = Query(default=None),
        vehicle_model: str | None = Query(default=None),
        vehicle_year: str | None = Query(default=None),
        alert_status: AlertStatus | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DetectionSearchResponse:
        results, total = service.search_detections(
            plate_query=plate,
            plate_match_mode=plate_match.value,
            start_timestamp_utc=start_utc,
            end_timestamp_utc=end_utc,
            camera_id=camera_id,
            min_latitude=min_latitude,
            max_latitude=max_latitude,
            min_longitude=min_longitude,
            max_longitude=max_longitude,
            vehicle_color=vehicle_color,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            vehicle_year=vehicle_year,
            alert_status=alert_status,
            limit=limit,
            offset=offset,
        )
        record_audit(
            request,
            principal=principal,
            action="search.detections",
            outcome=AuditOutcome.success,
            details={"plate": plate, "camera_id": camera_id, "limit": limit, "offset": offset, "total_results": total},
        )
        return DetectionSearchResponse(page=SearchPageInfo(total_results=total, limit=limit, offset=offset), results=results)

    @api_router.get("/search/alerts", response_model=AlertSearchResponse)
    def search_alerts(
        request: Request,
        plate: str | None = Query(default=None),
        plate_match: SearchPlateMatchMode = Query(default=SearchPlateMatchMode.contains),
        start_utc: str | None = Query(default=None),
        end_utc: str | None = Query(default=None),
        camera_id: str | None = Query(default=None),
        min_latitude: float | None = Query(default=None),
        max_latitude: float | None = Query(default=None),
        min_longitude: float | None = Query(default=None),
        max_longitude: float | None = Query(default=None),
        vehicle_color: str | None = Query(default=None),
        vehicle_make: str | None = Query(default=None),
        vehicle_model: str | None = Query(default=None),
        vehicle_year: str | None = Query(default=None),
        status_filter: AlertStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> AlertSearchResponse:
        results, total = service.search_alerts(
            plate_query=plate,
            plate_match_mode=plate_match.value,
            start_timestamp_utc=start_utc,
            end_timestamp_utc=end_utc,
            camera_id=camera_id,
            min_latitude=min_latitude,
            max_latitude=max_latitude,
            min_longitude=min_longitude,
            max_longitude=max_longitude,
            vehicle_color=vehicle_color,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            vehicle_year=vehicle_year,
            alert_status=status_filter,
            limit=limit,
            offset=offset,
        )
        record_audit(
            request,
            principal=principal,
            action="search.alerts",
            outcome=AuditOutcome.success,
            details={"plate": plate, "camera_id": camera_id, "limit": limit, "offset": offset, "total_results": total},
        )
        return AlertSearchResponse(page=SearchPageInfo(total_results=total, limit=limit, offset=offset), results=results)

    @api_router.get("/demo/runtime", response_model=DemoRuntimeStatus)
    def get_demo_runtime_status(
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DemoRuntimeStatus:
        return _build_demo_runtime_status(demo_manager.status())

    @api_router.post("/demo/runs", response_model=DemoRuntimeStatus, status_code=status.HTTP_202_ACCEPTED)
    def start_demo_run(
        request: Request,
        submission: DemoRunSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> DemoRuntimeStatus:
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
            record_audit(request, principal=principal, action="demo.run.start", outcome=AuditOutcome.rejected, details={"detail": str(exc)})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        record_audit(
            request,
            principal=principal,
            action="demo.run.start",
            outcome=AuditOutcome.success,
            details={"frames_directory": submission.frames_directory, "sequence_id": submission.sequence_id},
        )
        return _build_demo_runtime_status(run_status)

    @api_router.post("/follow-ups", response_model=FollowUpRecord, status_code=status.HTTP_201_CREATED)
    def create_follow_up(
        request: Request,
        submission: FollowUpSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> FollowUpRecord:
        now = _utcnow()
        follow_up = FollowUpRecord(
            follow_up_id=f"fu_{uuid4().hex[:12]}",
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            summary=submission.summary,
            notes=submission.notes,
            due_at_utc=submission.due_at_utc,
            created_at_utc=now,
            updated_at_utc=now,
        )
        try:
            created = service.create_follow_up(follow_up)
        except DetectionNotFoundError as exc:
            record_audit(
                request,
                principal=principal,
                action="follow_up.create",
                outcome=AuditOutcome.rejected,
                target_type="detection",
                target_id=submission.detection_id,
                details={"detail": "Detection not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        record_audit(
            request,
            principal=principal,
            action="follow_up.create",
            outcome=AuditOutcome.success,
            target_type="follow_up",
            target_id=created.follow_up_id,
            details={"detection_id": created.detection_id, "status": created.status.value},
        )
        return created

    @api_router.get("/follow-ups", response_model=list[FollowUpRecord])
    def list_follow_ups(
        detection_id: str | None = Query(default=None),
        status_filter: FollowUpStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[FollowUpRecord]:
        return service.list_follow_ups(detection_id=detection_id, status=status_filter, limit=limit)

    @api_router.get("/follow-ups/{follow_up_id}", response_model=FollowUpRecord)
    def get_follow_up(
        follow_up_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> FollowUpRecord:
        follow_up = service.get_follow_up(follow_up_id)
        if follow_up is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found")
        return follow_up

    @api_router.put("/follow-ups/{follow_up_id}", response_model=FollowUpRecord)
    def update_follow_up(
        request: Request,
        follow_up_id: str,
        submission: FollowUpSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> FollowUpRecord:
        existing = service.get_follow_up(follow_up_id)
        if existing is None:
            record_audit(
                request,
                principal=principal,
                action="follow_up.update",
                outcome=AuditOutcome.rejected,
                target_type="follow_up",
                target_id=follow_up_id,
                details={"detail": "Follow-up not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found")
        follow_up = FollowUpRecord(
            follow_up_id=existing.follow_up_id,
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=existing.created_by_operator_id or principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            summary=submission.summary,
            notes=submission.notes,
            due_at_utc=submission.due_at_utc,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_utcnow(),
        )
        try:
            updated = service.update_follow_up(follow_up)
        except DetectionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        except FollowUpNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found") from exc
        record_audit(
            request,
            principal=principal,
            action="follow_up.update",
            outcome=AuditOutcome.success,
            target_type="follow_up",
            target_id=follow_up_id,
            details={"detection_id": updated.detection_id, "status": updated.status.value},
        )
        return updated

    @api_router.post("/assignments", response_model=DispatchAssignmentRecord, status_code=status.HTTP_201_CREATED)
    def create_assignment(
        request: Request,
        submission: DispatchAssignmentSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> DispatchAssignmentRecord:
        now = _utcnow()
        assignment = DispatchAssignmentRecord(
            assignment_id=f"asg_{uuid4().hex[:12]}",
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            assigned_unit_label=submission.assigned_unit_label,
            destination_label=submission.destination_label,
            summary=submission.summary,
            notes=submission.notes,
            created_at_utc=now,
            updated_at_utc=now,
        )
        try:
            created = service.create_assignment(assignment)
        except DetectionNotFoundError as exc:
            record_audit(
                request,
                principal=principal,
                action="assignment.create",
                outcome=AuditOutcome.rejected,
                target_type="detection",
                target_id=submission.detection_id,
                details={"detail": "Detection not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        except AlertNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from exc
        record_audit(
            request,
            principal=principal,
            action="assignment.create",
            outcome=AuditOutcome.success,
            target_type="assignment",
            target_id=created.assignment_id,
            details={"detection_id": created.detection_id, "status": created.status.value},
        )
        return created

    @api_router.get("/assignments", response_model=list[DispatchAssignmentRecord])
    def list_assignments(
        detection_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[DispatchAssignmentRecord]:
        return service.list_assignments(detection_id=detection_id, limit=limit)

    @api_router.get("/assignments/{assignment_id}", response_model=DispatchAssignmentRecord)
    def get_assignment(
        assignment_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DispatchAssignmentRecord:
        assignment = service.get_assignment(assignment_id)
        if assignment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        return assignment

    @api_router.put("/assignments/{assignment_id}", response_model=DispatchAssignmentRecord)
    def update_assignment(
        request: Request,
        assignment_id: str,
        submission: DispatchAssignmentSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> DispatchAssignmentRecord:
        existing = service.get_assignment(assignment_id)
        if existing is None:
            record_audit(
                request,
                principal=principal,
                action="assignment.update",
                outcome=AuditOutcome.rejected,
                target_type="assignment",
                target_id=assignment_id,
                details={"detail": "Assignment not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        assignment = DispatchAssignmentRecord(
            assignment_id=existing.assignment_id,
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=existing.created_by_operator_id or principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            assigned_unit_label=submission.assigned_unit_label,
            destination_label=submission.destination_label,
            summary=submission.summary,
            notes=submission.notes,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_utcnow(),
        )
        try:
            updated = service.update_assignment(assignment)
        except DetectionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        except AlertNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from exc
        except AssignmentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found") from exc
        record_audit(
            request,
            principal=principal,
            action="assignment.update",
            outcome=AuditOutcome.success,
            target_type="assignment",
            target_id=assignment_id,
            details={"detection_id": updated.detection_id, "status": updated.status.value},
        )
        return updated

    @api_router.get("/detections", response_model=list[DetectionRecord])
    def list_detections(
        camera_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[DetectionRecord]:
        return service.list_detections(camera_id=camera_id, limit=limit)

    @api_router.get("/detections/{detection_id}", response_model=DetectionRecord)
    def get_detection(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DetectionRecord:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        return detection

    @api_router.get("/detections/{detection_id}/frame")
    def get_detection_frame(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> FileResponse:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        media_path = _resolve_media_path(detection.image_path, service.media_layout.root)
        if media_path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame image not found")
        return FileResponse(media_path)

    @api_router.get("/detections/{detection_id}/plate-crop")
    def get_detection_plate_crop(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> FileResponse:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        if not detection.plate_crop_path:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plate crop unavailable")
        media_path = _resolve_media_path(detection.plate_crop_path, service.media_layout.root)
        if media_path is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plate crop unavailable")
        return FileResponse(media_path)

    @api_router.post("/reviews/{detection_id}", response_model=ReviewRecord, status_code=status.HTTP_201_CREATED)
    def create_review(
        request: Request,
        detection_id: str,
        submission: ReviewSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> ReviewRecord:
        review = ReviewRecord(
            review_id=f"rev_{uuid4().hex[:12]}",
            detection_id=detection_id,
            action=submission.action,
            operator_id=submission.operator_id or principal.principal_id,
            corrected_plate_text=submission.corrected_plate_text,
            notes=submission.notes,
            reviewed_at_utc=submission.reviewed_at_utc,
        )
        try:
            created = service.create_review(review)
        except DetectionNotFoundError as exc:
            record_audit(
                request,
                principal=principal,
                action="review.create",
                outcome=AuditOutcome.rejected,
                target_type="detection",
                target_id=detection_id,
                details={"detail": "Detection not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        record_audit(
            request,
            principal=principal,
            action="review.create",
            outcome=AuditOutcome.success,
            target_type="detection",
            target_id=detection_id,
            details={"review_id": created.review_id, "action": created.action.value},
        )
        return created

    @api_router.get("/reviews/{detection_id}", response_model=list[ReviewRecord])
    def list_reviews(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[ReviewRecord]:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        return service.list_reviews(detection_id)

    @api_router.get("/alerts", response_model=list[AlertRecord])
    def list_alerts(
        camera_id: str | None = Query(default=None),
        status_filter: AlertStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[AlertRecord]:
        return service.list_alerts(camera_id=camera_id, status=status_filter, limit=limit)

    @api_router.get("/alerts/{alert_id}", response_model=AlertRecord)
    def get_alert(
        alert_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> AlertRecord:
        alert = service.get_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert

    @api_router.put("/alerts/{alert_id}", response_model=AlertRecord)
    def update_alert(
        request: Request,
        alert_id: str,
        submission: AlertUpdateSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> AlertRecord:
        existing = service.get_alert(alert_id)
        if existing is None:
            record_audit(request, principal=principal, action="alert.update", outcome=AuditOutcome.rejected, target_type="alert", target_id=alert_id, details={"detail": "Alert not found"})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        alert = AlertRecord(
            alert_id=existing.alert_id,
            detection_id=existing.detection_id,
            hotlist_entry_id=existing.hotlist_entry_id,
            timestamp_utc=existing.timestamp_utc,
            camera_id=existing.camera_id,
            matched_plate_text=existing.matched_plate_text,
            match_confidence=existing.match_confidence,
            match_type=existing.match_type,
            hotlist_label=existing.hotlist_label,
            notes=existing.notes,
            response_operator_id=submission.operator_id or principal.principal_id,
            response_notes=submission.response_notes,
            updated_at_utc=_utcnow(),
            status=submission.status,
            gps_latitude=existing.gps_latitude,
            gps_longitude=existing.gps_longitude,
        )
        try:
            updated = service.update_alert(alert)
        except AlertNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from exc
        record_audit(
            request,
            principal=principal,
            action="alert.update",
            outcome=AuditOutcome.success,
            target_type="alert",
            target_id=alert_id,
            details={"status": updated.status.value, "response_operator_id": updated.response_operator_id},
        )
        return updated

    @api_router.get("/hotlists", response_model=list[HotlistEntry])
    def list_hotlists(
        active_only: bool = Query(default=False),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[HotlistEntry]:
        return service.list_hotlists(active_only=active_only, limit=limit)

    @api_router.post("/hotlists", response_model=HotlistEntry, status_code=status.HTTP_201_CREATED)
    def create_hotlist(
        request: Request,
        submission: HotlistSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.admin_access),
    ) -> HotlistEntry:
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
        created = service.create_hotlist(entry)
        record_audit(request, principal=principal, action="hotlist.create", outcome=AuditOutcome.success, target_type="hotlist", target_id=created.entry_id, details={"plate_text": created.plate_text, "active": created.active})
        return created

    @api_router.put("/hotlists/{entry_id}", response_model=HotlistEntry)
    def update_hotlist(
        request: Request,
        entry_id: str,
        submission: HotlistSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.admin_access),
    ) -> HotlistEntry:
        existing = service.get_hotlist(entry_id)
        if existing is None:
            record_audit(request, principal=principal, action="hotlist.update", outcome=AuditOutcome.rejected, target_type="hotlist", target_id=entry_id, details={"detail": "Hotlist entry not found"})
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
            updated = service.update_hotlist(entry)
        except HotlistNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found") from exc
        record_audit(request, principal=principal, action="hotlist.update", outcome=AuditOutcome.success, target_type="hotlist", target_id=entry_id, details={"active": updated.active, "label": updated.label})
        return updated

    @api_router.delete("/hotlists/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_hotlist(
        request: Request,
        entry_id: str,
        principal: ApiPrincipalContext = Depends(access_controller.admin_access),
    ) -> Response:
        existing = service.get_hotlist(entry_id)
        if existing is None:
            record_audit(
                request,
                principal=principal,
                action="hotlist.delete",
                outcome=AuditOutcome.rejected,
                target_type="hotlist",
                target_id=entry_id,
                details={"detail": "Hotlist entry not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found")
        try:
            service.delete_hotlist(entry_id)
        except HotlistNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found") from exc
        record_audit(
            request,
            principal=principal,
            action="hotlist.delete",
            outcome=AuditOutcome.success,
            target_type="hotlist",
            target_id=entry_id,
            details={"plate_text": existing.plate_text},
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api_router.get("/audit/events", response_model=AuditEventResponse)
    def list_audit_events(
        limit: int = Query(default=100, ge=1, le=500),
        principal_id: str | None = Query(default=None),
        action_prefix: str | None = Query(default=None),
        outcome: AuditOutcome | None = Query(default=None),
        target_id: str | None = Query(default=None),
        _principal: ApiPrincipalContext = Depends(access_controller.audit_access),
    ) -> AuditEventResponse:
        events = audit_logger.list_events(
            limit=limit,
            principal_id=principal_id,
            action_prefix=action_prefix,
            outcome=outcome.value if outcome is not None else None,
            target_id=target_id,
        )
        return AuditEventResponse(events=events)

    canonical_prefix = deployment.api.versioning.canonical_prefix.rstrip("/")
    app.include_router(api_router, prefix=canonical_prefix)
    if deployment.api.versioning.enable_legacy_routes:
        app.include_router(api_router, include_in_schema=False)
    return app
