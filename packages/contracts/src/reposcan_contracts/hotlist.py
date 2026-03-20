"""Hotlist contract — entries managed via the API and consumed by the alerting service."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .types import PlateMatchType, UtcTimestamp


class HotlistEntry(BaseModel):
    """A single plate entry in the local hotlist.

    Created and managed via POST /hotlists and PUT /hotlists/{id}.
    The alerting service loads and evaluates entries against incoming detections.
    """

    entry_id: str = Field(..., description="Stable unique identifier for this hotlist entry")
    plate_text: str = Field(..., min_length=1, description="Plate text to watch for (normalized to uppercase)")
    label: Optional[str] = Field(None, description="Human-readable label, e.g. 'Stolen – Case 1234'")
    notes: Optional[str] = Field(None, description="Operator notes")
    active: bool = Field(True, description="Whether this entry is currently being matched")
    created_at_utc: UtcTimestamp = Field(..., description="Entry creation timestamp (ISO 8601 UTC)")
    updated_at_utc: UtcTimestamp = Field(..., description="Last update timestamp (ISO 8601 UTC)")

    @field_validator("plate_text")
    @classmethod
    def normalize_plate(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not normalized:
            raise ValueError("plate_text must not be blank after normalization")
        return normalized


class HotlistMatchResult(BaseModel):
    """Result of evaluating a plate text against the hotlist.

    Produced by the alerting service during detection processing.
    """

    matched: bool = Field(..., description="Whether any active hotlist entries were matched")
    entry_id: Optional[str] = Field(None, description="Matched entry identifier, or None if no match")
    match_type: Optional[PlateMatchType] = Field(None, description="'exact' or 'normalized' when matched")
    plate_text: str = Field(..., description="The plate text that was evaluated")
