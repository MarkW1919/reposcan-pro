"""API request models for the Phase 2 skeleton."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import HealthResponse
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.popup import PopupActivityEvent
from reposcan_contracts.review import ReviewAction
from reposcan_contracts.types import UtcTimestamp


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
    plate_text: str = Field(..., min_length=1, description="Plate text to watch for")
    label: Optional[str] = Field(None, description="Human-readable label")
    notes: Optional[str] = Field(None, description="Operator notes")
    active: bool = Field(True, description="Whether this entry should be actively matched")


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


class DashboardOverview(BaseModel):
    generated_at_utc: UtcTimestamp = Field(..., description="Overview generation timestamp")
    health: HealthResponse
    counts: DashboardCounts
    detections: list[DetectionRecord]
    alerts: list[AlertRecord]
    hotlists: list[HotlistEntry]
    popup_activity: list[PopupActivityEvent]
