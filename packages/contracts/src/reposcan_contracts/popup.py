"""Popup activity contract for operator-facing alert and scan feeds."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class PopupEventType(str, Enum):
    address = "address"
    hotlist = "hotlist"


class PopupActivityEvent(BaseModel):
    """A recent operator-facing popup event derived from live detections or alerts."""

    event_id: str = Field(..., description="Stable unique popup event identifier")
    event_type: PopupEventType = Field(..., description="Popup event type shown to the operator")
    source_record_id: str = Field(..., description="Backing alert or detection record identifier")
    detection_id: str = Field(..., description="Associated detection identifier")
    timestamp_utc: UtcTimestamp = Field(..., description="UTC timestamp of the popup event")
    camera_id: str = Field(..., description="Camera that produced the popup event")

    plate_text: Optional[str] = Field(None, description="Best available plate read for this popup")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Best confidence associated with the popup")

    vehicle_color: Optional[str] = Field(None, description="Predicted vehicle color when available")
    vehicle_make: Optional[str] = Field(None, description="Predicted vehicle make when available")
    vehicle_model: Optional[str] = Field(None, description="Predicted vehicle model when available")
    optional_vehicle_year: Optional[str] = Field(None, description="Vehicle year or year range when available")

    hotlist_label: Optional[str] = Field(None, description="Matched hotlist label for hotlist popups")
    gps_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    gps_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    note: Optional[str] = Field(None, description="Operator-facing context for the popup event")
