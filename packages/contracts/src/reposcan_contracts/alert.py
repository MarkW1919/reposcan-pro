"""Alert contract — hotlist match events and alert history records."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .types import PlateMatchType, UtcTimestamp


class AlertStatus(str, Enum):
    active = "active"
    acknowledged = "acknowledged"
    dismissed = "dismissed"


class AlertRecord(BaseModel):
    """A hotlist-match alert event stored by the alerting service.

    Created when a TrackedDetection plate matches a hotlist entry with
    sufficient confidence.
    """

    alert_id: str = Field(..., description="Stable unique alert identifier")
    detection_id: str = Field(..., description="Associated detection record")
    hotlist_entry_id: str = Field(..., description="Matched hotlist entry identifier")
    timestamp_utc: UtcTimestamp = Field(..., description="UTC timestamp of the alert event (ISO 8601)")
    camera_id: str = Field(..., description="Camera that produced the detection")

    matched_plate_text: str = Field(..., min_length=1, description="Plate text that triggered the match")
    match_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence of the plate match")
    match_type: PlateMatchType = Field(..., description="exact or normalized")

    hotlist_label: Optional[str] = Field(None, description="Human-readable label from the hotlist entry")
    notes: Optional[str] = Field(None, description="Operator notes attached to this alert")
    response_operator_id: Optional[str] = Field(None, description="Operator who responded to the alert")
    response_notes: Optional[str] = Field(None, description="Most recent response note for this alert")
    updated_at_utc: Optional[UtcTimestamp] = Field(
        None,
        description="UTC timestamp of the most recent alert response update",
    )

    status: AlertStatus = Field(AlertStatus.active)

    gps_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    gps_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
