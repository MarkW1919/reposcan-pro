"""Detection record contract — canonical schema for a single detection event.

This is the authoritative shape for detections flowing through storage, the API,
and the sync path.  All fields match API_CONTRACTS.md exactly.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .types import UtcTimestamp


class SyncStatus(str, Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"
    skipped = "skipped"


class BoundingBox(BaseModel):
    """Bounding box in source-frame pixel coordinates."""

    x: int = Field(..., ge=0, description="Left edge (pixels)")
    y: int = Field(..., ge=0, description="Top edge (pixels)")
    w: int = Field(..., gt=0, description="Width (pixels)")
    h: int = Field(..., gt=0, description="Height (pixels)")


class PlateCandidate(BaseModel):
    """A single OCR candidate returned by the inference pipeline."""

    text: str = Field(..., min_length=1, description="OCR text for this candidate")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0, 1]")


class DetectionRecord(BaseModel):
    """Canonical detection record.

    Produced by the storage service and consumed by the API and sync service.
    Matches the schema defined in docs/API_CONTRACTS.md.
    """

    detection_id: str = Field(..., description="Stable unique identifier for the detection event")
    timestamp_utc: UtcTimestamp = Field(..., description="UTC timestamp in ISO 8601 format")
    camera_id: str = Field(..., description="Logical camera identifier")

    # GPS — nullable when the camera has no location fix
    gps_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    gps_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

    # OCR results
    plate_text: Optional[str] = Field(None, description="Best promoted OCR read")
    plate_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    plate_candidates: list[PlateCandidate] = Field(
        default_factory=list, description="Alternate OCR candidates with confidence"
    )

    # Bounding boxes
    vehicle_bbox: BoundingBox = Field(..., description="Vehicle bbox in source-frame coordinates")
    plate_bbox: Optional[BoundingBox] = Field(None, description="Plate bbox in source-frame coordinates")

    # Vehicle attributes — nullable when model confidence is below threshold
    vehicle_color: Optional[str] = None
    vehicle_color_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    vehicle_make: Optional[str] = None
    vehicle_make_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    vehicle_model: Optional[str] = None
    vehicle_model_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Optional year prediction (only when enabled in pipeline config)
    optional_vehicle_year: Optional[str] = None
    optional_year_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Tracking
    tracker_id: Optional[str] = None

    # Media references
    image_path: str = Field(..., description="Local path or object reference to frame image")
    plate_crop_path: Optional[str] = Field(None, description="Local path to the best plate crop")
    source_video_path: Optional[str] = Field(None, description="Local reference to source snippet or file")

    # Frame metadata
    frame_number: int = Field(..., ge=0, description="Source frame index")

    # Sync state
    local_only_flag: bool = Field(True, description="True until sync policy clears it")
    sync_status: SyncStatus = Field(SyncStatus.pending)

    @field_validator("plate_confidence")
    @classmethod
    def confidence_requires_text(cls, v: Optional[float], info: object) -> Optional[float]:
        """plate_confidence must be absent when plate_text is absent."""
        # Accessing sibling fields via info.data (pydantic v2 pattern)
        data = getattr(info, "data", {})
        if v is not None and data.get("plate_text") is None:
            raise ValueError("plate_confidence must be None when plate_text is None")
        return v
