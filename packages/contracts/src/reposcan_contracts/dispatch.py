"""Dispatch assignment contract for coordinated alert handling."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .types import UtcTimestamp


class DispatchAssignmentPriority(str, Enum):
    watch = "watch"
    priority = "priority"
    critical = "critical"


class DispatchAssignmentStatus(str, Enum):
    queued = "queued"
    assigned = "assigned"
    en_route = "en_route"
    onsite = "onsite"
    completed = "completed"
    cancelled = "cancelled"


class DispatchAssignmentRecord(BaseModel):
    assignment_id: str = Field(..., min_length=1)
    detection_id: str = Field(..., min_length=1)
    alert_id: Optional[str] = Field(None, min_length=1)
    plate_text: Optional[str] = Field(None, min_length=1)
    priority: DispatchAssignmentPriority = DispatchAssignmentPriority.priority
    status: DispatchAssignmentStatus = DispatchAssignmentStatus.queued
    created_by_operator_id: Optional[str] = Field(None, min_length=1)
    assigned_operator_id: Optional[str] = Field(None, min_length=1)
    assigned_unit_label: Optional[str] = None
    destination_label: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    created_at_utc: UtcTimestamp
    updated_at_utc: UtcTimestamp

    @field_validator("plate_text")
    @classmethod
    def normalize_plate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None
