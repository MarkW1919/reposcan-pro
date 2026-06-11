"""Alert contract — hotlist match events and alert history records."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from .types import HotlistMatchKind, PlateMatchType, UtcTimestamp


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

    # Match kind. Defaults to ``plate`` so existing plate-match alerts and
    # their stored records are unchanged. ``in_zone_profile`` marks a geofenced
    # make/model lead (see HotlistMatchKind).
    match_kind: HotlistMatchKind = Field(
        HotlistMatchKind.plate, description="How the hotlist entry was matched"
    )
    # Plate fields are optional because a geofenced make/model lead may have no
    # matching/readable plate. They remain populated for every plate match.
    matched_plate_text: Optional[str] = Field(
        None, description="Plate text that triggered the match (plate matches only)"
    )
    match_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence/score of the match")
    match_type: Optional[PlateMatchType] = Field(
        None, description="exact or normalized (plate matches only)"
    )
    matched_attributes: list[str] = Field(
        default_factory=list,
        description="Attribute dimensions that matched, e.g. ['make', 'model', 'color'] for in-zone leads",
    )

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

    @model_validator(mode="after")
    def _validate_match_shape(self) -> "AlertRecord":
        # A plate-match alert must carry the plate text and type that triggered
        # it (preserves the original invariant). In-zone make/model leads have
        # no required plate, so the relaxation only applies to them.
        if self.match_kind == HotlistMatchKind.plate:
            if not self.matched_plate_text:
                raise ValueError("plate-match alerts require a non-empty matched_plate_text")
            if self.match_type is None:
                raise ValueError("plate-match alerts require a match_type")
        return self
