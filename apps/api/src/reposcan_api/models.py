"""API request models for the Phase 2 skeleton."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.health import HealthResponse
from reposcan_contracts.hotlist import HotlistEntry
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
