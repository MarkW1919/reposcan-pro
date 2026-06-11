"""Follow-up contract for pinned detections that need field attention."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .types import UtcTimestamp


class FollowUpPriority(str, Enum):
    routine = "routine"
    priority = "priority"
    critical = "critical"


class FollowUpStatus(str, Enum):
    open = "open"
    monitoring = "monitoring"
    resolved = "resolved"


class FollowUpRecord(BaseModel):
    follow_up_id: str = Field(..., min_length=1)
    detection_id: str = Field(..., min_length=1)
    alert_id: Optional[str] = Field(None, min_length=1)
    plate_text: Optional[str] = Field(None, min_length=1)
    priority: FollowUpPriority = FollowUpPriority.priority
    status: FollowUpStatus = FollowUpStatus.open
    created_by_operator_id: Optional[str] = Field(None, min_length=1)
    assigned_operator_id: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    notes: Optional[str] = None
    due_at_utc: Optional[UtcTimestamp] = None
    created_at_utc: UtcTimestamp
    updated_at_utc: UtcTimestamp

    @field_validator("plate_text")
    @classmethod
    def normalize_plate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None
