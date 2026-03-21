"""FrameEnvelope and PreparedFrame — inter-service contracts for image flow.

Produced by: services/capture
Consumed by: services/preprocessing

PreparedFrame is produced by preprocessing and consumed by inference.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class SourceType(str, Enum):
    rtsp = "rtsp"
    usb = "usb"
    file = "file"


class GpsSnapshot(BaseModel):
    """GPS fix attached to a frame at capture time."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: Optional[float] = Field(None, ge=0.0, description="Horizontal accuracy in metres")
    altitude_m: Optional[float] = Field(None, description="Altitude in metres above sea level")


class CameraProfile(BaseModel):
    """Camera-level metadata forwarded with every frame.

    Populated from the camera config and attached by the capture service so
    downstream stages do not need to re-read the config file per frame.
    """

    camera_id: str
    display_name: Optional[str] = None
    source_type: SourceType
    sensor_type: Optional[str] = None
    resolution_w: Optional[int] = Field(None, gt=0)
    resolution_h: Optional[int] = Field(None, gt=0)
    fps: Optional[float] = Field(None, gt=0.0)
    ir_mode: bool = False
    gps_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    gps_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)


class FrameEnvelope(BaseModel):
    """Normalized frame container passed from capture to preprocessing.

    frame_path points to the raw frame on the shared local filesystem.
    All downstream services treat this path as read-only.
    """

    frame_id: str = Field(..., description="Stable unique identifier for this frame")
    camera_id: str = Field(..., description="Logical camera identifier")
    timestamp_utc: UtcTimestamp = Field(..., description="Capture timestamp (ISO 8601 UTC)")
    frame_path: str = Field(..., description="Local path to the captured frame image")
    frame_number: int = Field(..., ge=0, description="Monotonic frame counter from this camera")
    source_type: SourceType
    camera_profile: CameraProfile
    gps_snapshot: Optional[GpsSnapshot] = Field(
        None, description="GPS fix at capture time, when available"
    )
    sequence_id: Optional[str] = Field(
        None, description="Session or recording identifier for grouping frames"
    )


class PreprocessingMetadata(BaseModel):
    """Summary of preprocessing decisions made for a frame."""

    artifact_generated: bool = False
    denoise_applied: bool = False
    contrast_enhanced: bool = False
    night_mode_triggered: bool = False
    mean_brightness_before: Optional[float] = Field(None, ge=0.0, le=255.0)
    mean_brightness_after: Optional[float] = Field(None, ge=0.0, le=255.0)


class PreparedFrame(BaseModel):
    """Inference-ready frame produced by preprocessing.

    raw_frame_path always preserves the original capture evidence path.
    prepared_frame_path points to the artifact that inference should consume.
    """

    frame_id: str = Field(..., description="Stable unique identifier for this frame")
    camera_id: str = Field(..., description="Logical camera identifier")
    timestamp_utc: UtcTimestamp = Field(..., description="Capture timestamp (ISO 8601 UTC)")
    raw_frame_path: str = Field(..., description="Original captured frame path")
    prepared_frame_path: str = Field(..., description="Inference-ready frame path")
    frame_number: int = Field(..., ge=0, description="Monotonic frame counter from this camera")
    source_type: SourceType
    camera_profile: CameraProfile
    gps_snapshot: Optional[GpsSnapshot] = Field(
        None, description="GPS fix at capture time, when available"
    )
    sequence_id: Optional[str] = Field(
        None, description="Session or recording identifier for grouping frames"
    )
    preprocessing: PreprocessingMetadata = Field(default_factory=PreprocessingMetadata)
