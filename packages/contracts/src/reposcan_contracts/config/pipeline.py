"""Pipeline configuration schema.

Loaded from configs/pipelines/*.yaml by the inference and tracking services.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlateDetectionStrategy(str, Enum):
    full_frame = "full_frame"
    vehicle_crop = "vehicle_crop"
    both = "both"


class NightModePolicy(str, Enum):
    auto = "auto"
    always = "always"
    never = "never"


class PreprocessingBackend(str, Enum):
    auto = "auto"
    pillow = "pillow"
    opencv = "opencv"


class OcrAggregation(str, Enum):
    majority_vote = "majority_vote"
    best_confidence = "best_confidence"
    ensemble = "ensemble"


class TrackingAlgorithm(str, Enum):
    byte_tracker = "byte_tracker"
    sort = "sort"
    deep_sort = "deep_sort"


class PreprocessingConfig(BaseModel):
    enabled: bool = True
    enhancement_backend: PreprocessingBackend = PreprocessingBackend.auto
    denoise: bool = True
    denoise_strength: float = Field(0.5, ge=0.0, le=1.0)
    exposure_compensation: bool = True
    target_mean_brightness: float = Field(90.0, ge=0.0, le=255.0)
    contrast_enhancement: bool = True
    contrast_clip_limit: float = Field(2.0, gt=0.0)
    clahe_tile_grid_size: int = Field(8, ge=2, le=32)
    night_mode_threshold_lux: Optional[float] = Field(
        10.0, ge=0.0, description="Lux level below which night preprocessing activates"
    )
    ir_night_mode: NightModePolicy = NightModePolicy.auto
    rectify_plate_crops: bool = True


class ThresholdConfig(BaseModel):
    vehicle_detection_min_confidence: float = Field(0.4, ge=0.0, le=1.0)
    plate_detection_min_confidence: float = Field(0.5, ge=0.0, le=1.0)
    ocr_min_confidence: float = Field(0.6, ge=0.0, le=1.0)
    classification_min_confidence: float = Field(0.5, ge=0.0, le=1.0)
    alert_min_plate_confidence: float = Field(
        0.7, ge=0.0, le=1.0,
        description="Minimum plate confidence before alerting service evaluates a detection"
    )
    geofence_radius_feet: float = Field(
        300.0, gt=0.0,
        description="Radius around a hotlist target address within which make/model in-zone leads fire"
    )


class TrackingConfig(BaseModel):
    enabled: bool = True
    algorithm: TrackingAlgorithm = TrackingAlgorithm.byte_tracker
    max_lost_frames: int = Field(30, gt=0, description="Frames before a lost track is terminated")
    min_hits_to_confirm: int = Field(3, gt=0, description="Minimum detections to confirm a track")
    ocr_aggregation: OcrAggregation = OcrAggregation.majority_vote
    min_match_iou: float = Field(0.05, ge=0.0, le=1.0, description="Minimum IoU used for candidate track matching")
    camera_motion_tolerance_px: float = Field(
        72.0,
        ge=0.0,
        description="Extra center-distance tolerance used when camera motion or rapid object motion is expected",
    )
    duplicate_suppression_window_seconds: float = Field(
        12.0,
        ge=0.0,
        description="Window for suppressing repeated same-plate detections from the same camera",
    )
    duplicate_suppression_min_plate_confidence: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Minimum promoted plate confidence before duplicate suppression is applied",
    )
    duplicate_suppression_min_iou: float = Field(
        0.2,
        ge=0.0,
        le=1.0,
        description="Minimum bbox IoU used when deciding whether a repeated same-plate detection is a duplicate",
    )


class FusionConfig(BaseModel):
    promote_best_read_threshold: float = Field(
        0.8, ge=0.0, le=1.0,
        description="Confidence threshold for promoting a read as the canonical plate text"
    )
    min_ocr_candidates_for_promotion: int = Field(
        2, ge=1, description="Minimum OCR reads before promotion is attempted"
    )
    max_candidate_age_frames: int = Field(
        90, gt=0, description="Oldest OCR read (in frames) still eligible for promotion"
    )


class PipelineConfig(BaseModel):
    """Complete pipeline configuration loaded from configs/pipelines/*.yaml."""

    pipeline_name: str = Field(..., description="Identifier for this pipeline configuration")
    description: Optional[str] = None
    plate_detection_strategy: PlateDetectionStrategy = PlateDetectionStrategy.vehicle_crop
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
