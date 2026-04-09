"""API request models for the Phase 2 skeleton."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.dispatch import DispatchAssignmentPriority, DispatchAssignmentRecord, DispatchAssignmentStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpPriority, FollowUpRecord, FollowUpStatus
from reposcan_contracts.health import CameraHealthRecord, HealthResponse
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorPrincipal, OperatorSessionRecord
from reposcan_contracts.popup import PopupActivityEvent
from reposcan_contracts.review import ReviewAction
from reposcan_contracts.types import UtcTimestamp
from reposcan_contracts.alert import AlertStatus


class ReviewSubmission(BaseModel):
    action: ReviewAction = Field(..., description="Review action to apply to this detection")
    operator_id: Optional[str] = Field(None, description="Operator identity when available")
    corrected_plate_text: Optional[str] = Field(
        None,
        description="Corrected plate text when action='correct'",
    )
    notes: Optional[str] = Field(None, description="Free-form operator notes")
    reviewed_at_utc: UtcTimestamp = Field(..., description="UTC timestamp of the review action")

    @model_validator(mode="after")
    def validate_correction_requirements(self) -> "ReviewSubmission":
        if self.action == ReviewAction.correct and not self.corrected_plate_text:
            raise ValueError("corrected_plate_text is required when action is 'correct'")
        return self


class HotlistSubmission(BaseModel):
    plate_text: Optional[str] = Field(None, min_length=1, description="Plate text to watch for")
    vin: Optional[str] = Field(None, min_length=1, description="Vehicle identification number")
    vehicle_year: Optional[str] = Field(None, min_length=1, description="Target vehicle year")
    vehicle_make: Optional[str] = Field(None, min_length=1, description="Target vehicle make")
    vehicle_model: Optional[str] = Field(None, min_length=1, description="Target vehicle model")
    vehicle_color: Optional[str] = Field(None, min_length=1, description="Target vehicle color")
    address_label: Optional[str] = Field(None, description="Short address or lot label")
    address_line1: Optional[str] = Field(None, description="Primary target address line")
    address_line2: Optional[str] = Field(None, description="Secondary target address line")
    address_city: Optional[str] = Field(None, description="Target address city")
    address_state: Optional[str] = Field(None, min_length=1, description="Target address state")
    address_postal_code: Optional[str] = Field(None, min_length=1, description="Target address postal code")
    address_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Optional target latitude")
    address_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Optional target longitude")
    label: Optional[str] = Field(None, description="Human-readable repo label")
    notes: Optional[str] = Field(None, description="Recovery instructions and operator notes")
    active: bool = Field(True, description="Whether this entry should be actively matched")

    @model_validator(mode="after")
    def validate_lookup_fields(self) -> "HotlistSubmission":
        has_plate = bool(self.plate_text and self.plate_text.strip())
        has_vin = bool(self.vin and self.vin.strip())
        has_vehicle_profile = bool(
            self.vehicle_make
            and self.vehicle_make.strip()
            and self.vehicle_model
            and self.vehicle_model.strip()
        )
        if not (has_plate or has_vin or has_vehicle_profile):
            raise ValueError("at least one of plate_text, vin, or vehicle_make + vehicle_model is required")
        return self


class AlertUpdateSubmission(BaseModel):
    status: AlertStatus = Field(..., description="Next status for the alert")
    operator_id: Optional[str] = Field(None, description="Operator updating the alert")
    response_notes: Optional[str] = Field(None, description="Response or disposition notes")


class FollowUpSubmission(BaseModel):
    detection_id: str = Field(..., min_length=1)
    alert_id: Optional[str] = Field(None, min_length=1)
    plate_text: Optional[str] = Field(None, min_length=1)
    priority: FollowUpPriority = FollowUpPriority.priority
    status: FollowUpStatus = FollowUpStatus.open
    assigned_operator_id: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    notes: Optional[str] = None
    due_at_utc: Optional[UtcTimestamp] = None


class DispatchAssignmentSubmission(BaseModel):
    detection_id: str = Field(..., min_length=1)
    alert_id: Optional[str] = Field(None, min_length=1)
    plate_text: Optional[str] = Field(None, min_length=1)
    priority: DispatchAssignmentPriority = DispatchAssignmentPriority.priority
    status: DispatchAssignmentStatus = DispatchAssignmentStatus.queued
    assigned_operator_id: Optional[str] = Field(None, min_length=1)
    assigned_unit_label: Optional[str] = None
    destination_label: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None


class OperatorSessionHeartbeatSubmission(BaseModel):
    session_id: str = Field(..., min_length=1)
    client_label: Optional[str] = None
    workspace: str = Field(..., min_length=1)
    selected_detection_id: Optional[str] = Field(None, min_length=1)
    selected_alert_id: Optional[str] = Field(None, min_length=1)
    destination_label: Optional[str] = None
    arrival_radius_feet: Optional[int] = Field(None, ge=1)
    idle_scan_enabled: bool = False
    visible_map_layers: list[str] = Field(default_factory=list)
    navigation_active: bool = False


class GeoShapeType(str, Enum):
    circle = "circle"
    polygon = "polygon"


class GeoSearchFilters(BaseModel):
    geo_shape: GeoShapeType | None = Field(None, description="Geo filter type")
    geo_center_latitude: float | None = Field(None, ge=-90.0, le=90.0)
    geo_center_longitude: float | None = Field(None, ge=-180.0, le=180.0)
    geo_radius_meters: float | None = Field(None, gt=0.0)
    geo_polygon_latitude: list[float] = Field(default_factory=list)
    geo_polygon_longitude: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_polygon_coordinate_lengths(self) -> "GeoSearchFilters":
        if len(self.geo_polygon_latitude) != len(self.geo_polygon_longitude):
            raise ValueError("geo_polygon_latitude and geo_polygon_longitude must contain the same number of points")
        return self

    def polygon_points(self) -> list[tuple[float, float]]:
        return list(zip(self.geo_polygon_latitude, self.geo_polygon_longitude, strict=False))


class DemoRunSubmission(BaseModel):
    frames_directory: str = Field(..., min_length=1, description="Local directory containing demo frames")
    start_timestamp_utc: Optional[UtcTimestamp] = Field(
        None,
        description="Optional override for the simulated first-frame timestamp",
    )
    frame_interval_ms: float = Field(100.0, gt=0.0, description="Milliseconds between simulated frames")
    glob_pattern: str = Field("*.jpg", min_length=1, description="Glob used to select frame files")
    start_frame_number: int = Field(0, ge=0, description="First frame number for the simulated sequence")
    sequence_id: Optional[str] = Field(None, description="Optional grouping identifier for the run")
    plate_text: str = Field("6BZN220", min_length=1, description="Deterministic demo plate text")


class DemoRunSummary(BaseModel):
    frames_captured: int = Field(..., ge=0)
    candidates_processed: int = Field(..., ge=0)
    tracks_finalized: int = Field(..., ge=0)
    stored_detection_ids: list[str]
    created_alert_ids: list[str]


class DemoRuntimeStatus(BaseModel):
    state: str = Field(..., description="idle, running, succeeded, or failed")
    run_id: Optional[str] = None
    started_at_utc: Optional[UtcTimestamp] = None
    completed_at_utc: Optional[UtcTimestamp] = None
    frames_directory: Optional[str] = None
    glob_pattern: Optional[str] = None
    sequence_id: Optional[str] = None
    plate_text: Optional[str] = None
    error_message: Optional[str] = None
    summary: Optional[DemoRunSummary] = None


class DashboardCounts(BaseModel):
    active_alerts: int = Field(..., ge=0)
    recent_detections: int = Field(..., ge=0)
    active_hotlists: int = Field(..., ge=0)
    open_follow_ups: int = Field(..., ge=0)
    active_assignments: int = Field(..., ge=0)
    active_sessions: int = Field(..., ge=0)


class DashboardOverview(BaseModel):
    generated_at_utc: UtcTimestamp = Field(..., description="Overview generation timestamp")
    health: HealthResponse
    camera_health: list[CameraHealthRecord]
    counts: DashboardCounts
    detections: list[DetectionRecord]
    alerts: list[AlertRecord]
    follow_ups: list[FollowUpRecord]
    assignments: list[DispatchAssignmentRecord]
    hotlists: list[HotlistEntry]
    popup_activity: list[PopupActivityEvent]
    current_principal: OperatorPrincipal
    active_sessions: list[OperatorSessionRecord]


class SearchPlateMatchMode(str, Enum):
    contains = "contains"
    exact = "exact"
    prefix = "prefix"
    suffix = "suffix"


class SearchPageInfo(BaseModel):
    total_results: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class DetectionSearchResponse(BaseModel):
    page: SearchPageInfo
    results: list[DetectionRecord]


class AlertSearchResponse(BaseModel):
    page: SearchPageInfo
    results: list[AlertRecord]


class ApiVersionInfo(BaseModel):
    service: str = Field(..., description="Logical service identifier")
    package_version: str = Field(..., description="Application package version")
    api_version: str = Field(..., description="Current external API version label")
    canonical_prefix: str = Field(..., description="Canonical route prefix for supported endpoints")
    legacy_routes_enabled: bool = Field(..., description="Whether unversioned compatibility aliases are active")
    auth_enabled: bool = Field(..., description="Whether API authentication is required for non-public routes")
    rate_limit_enabled: bool = Field(..., description="Whether request throttling is active")


class AuditOutcome(str, Enum):
    success = "success"
    denied = "denied"
    rejected = "rejected"
    error = "error"


class ApiAuditEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    occurred_at_utc: UtcTimestamp
    request_id: str = Field(..., min_length=1)
    principal_id: str | None = None
    principal_roles: list[str] = Field(default_factory=list)
    action: str = Field(..., min_length=1)
    outcome: AuditOutcome
    method: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    target_type: str | None = None
    target_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditEventResponse(BaseModel):
    events: list[ApiAuditEvent]
