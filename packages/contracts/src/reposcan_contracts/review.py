"""Review contract — operator review and OCR correction actions.

Consumed by POST /reviews/{id}.  Review state is durable locally.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from .types import UtcTimestamp


class ReviewAction(str, Enum):
    confirm = "confirm"      # operator confirms the existing read is correct
    correct = "correct"      # operator provides a corrected plate text
    flag = "flag"            # operator flags for further human review
    dismiss = "dismiss"      # operator dismisses as a false positive


class ReviewRecord(BaseModel):
    """A review action taken by an operator on a detection.

    Stored alongside the detection record.  Multiple reviews may be chained
    over time (e.g. flag → correct).
    """

    review_id: str = Field(..., description="Stable unique review identifier")
    detection_id: str = Field(..., description="The detection this review is attached to")
    action: ReviewAction = Field(..., description="The review action taken")
    operator_id: Optional[str] = Field(None, description="Operator who performed the review (when auth is active)")
    corrected_plate_text: Optional[str] = Field(
        None, description="New plate text when action=correct"
    )
    notes: Optional[str] = Field(None, description="Free-form operator notes")
    reviewed_at_utc: UtcTimestamp = Field(..., description="UTC timestamp of the review action (ISO 8601)")

    @model_validator(mode="after")
    def validate_correction_requirements(self) -> "ReviewRecord":
        if self.action == ReviewAction.correct and not self.corrected_plate_text:
            raise ValueError("corrected_plate_text is required when action is 'correct'")
        return self
