"""Hotlist contract - entries managed via the API and consumed by the alerting service."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .types import HotlistMatchKind, PlateMatchType, UtcTimestamp


class HotlistEntry(BaseModel):
    """A single repo account / watch entry in local storage.

    Created and managed via POST /hotlists and PUT /hotlists/{id}.
    The alerting service currently evaluates only plate-bearing entries against
    incoming detections. VIN, vehicle profile, and address fields exist for
    repo-order intake, locate workflows, and future matching expansion.
    """

    entry_id: str = Field(..., description="Stable unique identifier for this hotlist entry")
    plate_text: Optional[str] = Field(None, min_length=1, description="Plate text to watch for (normalized to uppercase)")
    plate_state: Optional[str] = Field(
        None,
        min_length=2,
        max_length=2,
        description="2-letter plate jurisdiction (corroboration/disambiguation only; never gates a plate match)",
    )
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

    @field_validator("plate_state")
    @classmethod
    def normalize_plate_state(cls, value: Optional[str]) -> Optional[str]:
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
    """Result of evaluating a detection against the hotlist.

    Produced by the alerting service during detection processing. Covers both
    plate matches (anywhere) and geofenced make/model leads (in-zone only).
    """

    matched: bool = Field(..., description="Whether any active hotlist entries were matched")
    entry_id: Optional[str] = Field(None, description="Matched entry identifier, or None if no match")
    match_kind: Optional[HotlistMatchKind] = Field(
        None, description="'plate' or 'in_zone_profile' when matched"
    )
    match_type: Optional[PlateMatchType] = Field(None, description="'exact' or 'normalized' for plate matches")
    score: float = Field(0.0, ge=0.0, le=1.0, description="Composite match confidence score")
    matched_dimensions: list[str] = Field(
        default_factory=list,
        description="Dimensions that matched, e.g. ['plate'] or ['make', 'model', 'color']",
    )
    plate_text: str = Field(..., description="The plate text that was evaluated")


class ScanArmMode(str, Enum):
    """How an ephemeral quick-scan target is armed.

    ``in_zone`` — arms only inside the configured radius of the target address
    (the driver entered a destination and is navigating there).
    ``manual`` — the driver explicitly armed it; scans everywhere until cleared.
    """

    in_zone = "in_zone"
    manual = "manual"


class QuickScanTarget(BaseModel):
    """An ephemeral, non-persisted 'look for this here, now' scan target.

    Lets a driver enter a plate / state / year-make-model alongside a
    destination (or arm it manually) without creating a saved hotlist account.
    Any combination of criteria may be set; an all-blank target is just plain
    navigation with nothing to scan for (``has_scan_criteria`` is False).

    It reuses the entire hotlist matching engine via ``to_hotlist_entry`` — a
    quick target is matched exactly like a transient HotlistEntry, so plate
    (CONFIRMED) and geofenced make/model (IN-ZONE LEAD) behave identically.
    """

    plate_text: Optional[str] = Field(None, min_length=1)
    plate_state: Optional[str] = Field(None, min_length=2, max_length=2)
    vehicle_year: Optional[str] = Field(None, min_length=1)
    vehicle_make: Optional[str] = Field(None, min_length=1)
    vehicle_model: Optional[str] = Field(None, min_length=1)
    vehicle_color: Optional[str] = Field(None, min_length=1)
    arm_mode: ScanArmMode = ScanArmMode.in_zone
    # Destination geozone (in_zone mode only). Manual mode ignores these.
    address_label: Optional[str] = None
    address_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    address_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

    @field_validator("plate_text")
    @classmethod
    def _normalize_plate(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip().upper() or None

    @field_validator("plate_state")
    @classmethod
    def _normalize_state(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip().upper() or None

    @field_validator("vehicle_year", "vehicle_make", "vehicle_model", "vehicle_color", "address_label")
    @classmethod
    def _normalize_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    def has_scan_criteria(self) -> bool:
        """True when there's something to actually scan for."""
        return bool(self.plate_text or (self.vehicle_make and self.vehicle_model))

    def to_hotlist_entry(self, *, entry_id: str, timestamp: str) -> Optional["HotlistEntry"]:
        """Adapt to a transient (non-persisted) HotlistEntry for matching.

        Returns None when there is nothing to scan for, so callers can treat an
        all-blank target as plain navigation.
        """
        if not self.has_scan_criteria():
            return None
        return HotlistEntry(
            entry_id=entry_id,
            plate_text=self.plate_text,
            plate_state=self.plate_state,
            vehicle_year=self.vehicle_year,
            vehicle_make=self.vehicle_make,
            vehicle_model=self.vehicle_model,
            vehicle_color=self.vehicle_color,
            address_label=self.address_label,
            address_latitude=self.address_latitude,
            address_longitude=self.address_longitude,
            label=self.address_label or "Quick scan target",
            active=True,
            created_at_utc=timestamp,
            updated_at_utc=timestamp,
        )
