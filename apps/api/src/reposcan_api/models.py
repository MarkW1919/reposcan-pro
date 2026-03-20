"""API request models for the Phase 2 skeleton."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

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
