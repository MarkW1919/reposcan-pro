"""InferenceCandidate — inter-service contract from inference to tracking/storage.

Produced by: services/inference
Consumed by: services/tracking, services/storage
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .detection import BoundingBox, PlateCandidate


class VehicleDetection(BaseModel):
    """A single vehicle detection from the vehicle detector model."""

    bbox: BoundingBox
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_label: str = Field(..., description="Detected class, e.g. 'car', 'truck'")


class PlateDetection(BaseModel):
    """A plate region detected within a vehicle crop or full frame."""

    bbox: BoundingBox
    confidence: float = Field(..., ge=0.0, le=1.0)
    vehicle_index: Optional[int] = Field(
        None, description="Index into vehicle_detections this plate belongs to, if known"
    )


class AttributePredictions(BaseModel):
    """Vehicle attribute predictions from the classifier model."""

    color: Optional[str] = None
    color_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    make: Optional[str] = None
    make_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    model_label: Optional[str] = Field(None, alias="model", description="Vehicle model label")
    model_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    year: Optional[str] = None
    year_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class ModelVersions(BaseModel):
    """Model artifact versions used during this inference pass.

    Stored alongside detections for reproducibility and audit.
    """

    vehicle_detector: Optional[str] = None
    plate_detector: Optional[str] = None
    ocr: Optional[str] = None
    classifier: Optional[str] = None


class InferenceCandidate(BaseModel):
    """Full output of a single inference pass on one frame.

    Passed from the inference service to the tracking and storage services.
    """

    frame_id: str = Field(..., description="Frame this inference was run on")
    camera_id: str = Field(..., description="Source camera identifier")
    timestamp_utc: str = Field(..., description="Frame capture timestamp (ISO 8601 UTC)")

    vehicle_detections: list[VehicleDetection] = Field(default_factory=list)
    plate_detections: list[PlateDetection] = Field(default_factory=list)
    ocr_candidates: list[PlateCandidate] = Field(
        default_factory=list, description="Raw OCR candidates across all plate regions"
    )
    attribute_predictions: list[AttributePredictions] = Field(
        default_factory=list, description="Per-vehicle attribute predictions (parallel with vehicle_detections)"
    )

    model_versions: ModelVersions = Field(default_factory=ModelVersions)
    processing_latency_ms: float = Field(..., ge=0.0, description="Total inference latency for this frame")
