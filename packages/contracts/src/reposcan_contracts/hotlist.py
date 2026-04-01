"""Hotlist contract - entries managed via the API and consumed by the alerting service."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .types import PlateMatchType, UtcTimestamp


class HotlistEntry(BaseModel):
    """A single repo account / watch entry in local storage.

    Created and managed via POST /hotlists and PUT /hotlists/{id}.
    The alerting service currently evaluates only plate-bearing entries against
    incoming detections. VIN, vehicle profile, and address fields exist for
    repo-order intake, locate workflows, and future matching expansion.
    """

    entry_id: str = Field(..., description="Stable unique identifier for this hotlist entry")
    plate_text: Optional[str] = Field(None, min_length=1, description="Plate text to watch for (normalized to uppercase)")
    vin: Optional[str] = Field(None, min_length=1, description="Vehicle identification number for repo intake")
    vehicle_year: Optional[str] = Field(None, min_length=1, description="Target vehicle year when plate is unknown")
    vehicle_make: Optional[str] = Field(None, min_length=1, description="Target vehicle make")
    vehicle_model: Optional[str] = Field(None, min_length=1, description="Target vehicle model")
    vehicle_color: Optional[str] = Field(None, min_length=1, description="Target vehicle color")
    address_label: Optional[str] = Field(None, description="Short address or lot label")
    address_line1: Optional[str] = Field(None, description="Primary target address line")
    address_line2: Optional[str] = Field(None, description="Secondary target address line")
    address_city: Optional[str] = Field(None, description="Target address city")
    address_state: Optional[str] = Field(None, min_length=1, description="Target address state or region")
    address_postal_code: Optional[str] = Field(None, min_length=1, description="Target address postal code")
    address_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Optional target latitude")
    address_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Optional target longitude")
    label: Optional[str] = Field(None, description="Human-readable repo label, e.g. lender or case identifier")
    notes: Optional[str] = Field(None, description="Recovery instructions and operator notes")
    active: bool = Field(True, description="Whether this entry is currently being matched")
    created_at_utc: UtcTimestamp = Field(..., description="Entry creation timestamp (ISO 8601 UTC)")
    updated_at_utc: UtcTimestamp = Field(..., description="Last update timestamp (ISO 8601 UTC)")

    @field_validator("plate_text")
    @classmethod
    def normalize_plate(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("vin")
    @classmethod
    def normalize_vin(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator(
        "vehicle_year",
        "vehicle_make",
        "vehicle_model",
        "vehicle_color",
        "address_label",
        "address_line1",
        "address_line2",
        "address_city",
        "address_postal_code",
        "label",
        "notes",
    )
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("address_state")
    @classmethod
    def normalize_address_state(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @model_validator(mode="after")
    def validate_lookup_fields(self) -> "HotlistEntry":
        has_plate = bool(self.plate_text)
        has_vin = bool(self.vin)
        has_vehicle_profile = bool(self.vehicle_make and self.vehicle_model)
        if not (has_plate or has_vin or has_vehicle_profile):
            raise ValueError("at least one of plate_text, vin, or vehicle_make + vehicle_model is required")
        return self


class HotlistMatchResult(BaseModel):
    """Result of evaluating a plate text against the hotlist.

    Produced by the alerting service during detection processing.
    """

    matched: bool = Field(..., description="Whether any active hotlist entries were matched")
    entry_id: Optional[str] = Field(None, description="Matched entry identifier, or None if no match")
    match_type: Optional[PlateMatchType] = Field(None, description="'exact' or 'normalized' when matched")
    plate_text: str = Field(..., description="The plate text that was evaluated")
