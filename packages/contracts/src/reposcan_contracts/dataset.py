"""Dataset intake and split contracts for training workflows."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from .types import UtcTimestamp


class DatasetTask(str, Enum):
    vehicle_detection = "vehicle_detection"
    plate_detection = "plate_detection"
    plate_ocr = "plate_ocr"
    vehicle_color_classification = "vehicle_color_classification"
    vehicle_make_model_classification = "vehicle_make_model_classification"
    vehicle_year_classification = "vehicle_year_classification"


class DatasetFormat(str, Enum):
    generic_capture = "generic_capture"
    yolo_detection = "yolo_detection"
    ocr_manifest = "ocr_manifest"
    imagefolder = "imagefolder"
    eval_holdout = "eval_holdout"


class DatasetSourceKind(str, Enum):
    field_capture = "field_capture"
    public_benchmark = "public_benchmark"
    synthetic = "synthetic"
    vendor_drop = "vendor_drop"
    internal_generated = "internal_generated"


class DatasetLicenseTier(str, Enum):
    internal = "internal"
    public = "public"
    commercial = "commercial"
    restricted = "restricted"
    unknown = "unknown"


class DatasetReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    quarantined = "quarantined"


class DatasetSplit(str, Enum):
    train = "train"
    validation = "validation"
    holdout = "holdout"
    field_eval = "field_eval"


class AnnotationTask(str, Enum):
    vehicle_detection = "vehicle_detection"
    plate_detection = "plate_detection"
    plate_ocr = "plate_ocr"
    vehicle_color = "vehicle_color"
    vehicle_make = "vehicle_make"
    vehicle_model = "vehicle_model"
    vehicle_year = "vehicle_year"


class LightingCondition(str, Enum):
    daylight = "daylight"
    dusk = "dusk"
    night = "night"
    no_light = "no_light"
    ir_assisted = "ir_assisted"
    glare = "glare"
    unknown = "unknown"


class DistanceBand(str, Enum):
    near = "near"
    medium = "medium"
    long_range = "long_range"


def _validate_relative_path(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("path must not be blank")
    if Path(normalized).is_absolute():
        raise ValueError("path must be relative")
    return normalized.replace("\\", "/")


def _normalize_version(value) -> str | None:
    if value is None:
        return None
    return str(value)


class DatasetProvenance(BaseModel):
    source_name: str = Field(..., min_length=1)
    source_kind: DatasetSourceKind
    license_tier: DatasetLicenseTier = DatasetLicenseTier.unknown
    license_name: str = Field(..., min_length=1)
    license_reference: str = Field(..., min_length=1)
    region: str | None = None
    collected_by: str | None = None
    collection_start_utc: UtcTimestamp | None = None
    collection_end_utc: UtcTimestamp | None = None
    notes: str | None = None


class AnnotationReview(BaseModel):
    reviewer: str = Field(..., min_length=1)
    reviewed_at_utc: UtcTimestamp
    accepted_tasks: list[AnnotationTask] = Field(default_factory=list)
    notes: str | None = None


class DatasetAssetRecord(BaseModel):
    asset_id: str = Field(..., min_length=1)
    relative_path: str = Field(..., min_length=1)
    capture_session_id: str = Field(..., min_length=1)
    timestamp_utc: UtcTimestamp | None = None
    lighting_conditions: list[LightingCondition] = Field(default_factory=list, min_length=1)
    distance_band: DistanceBand | None = None
    annotations: list[AnnotationTask] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    expected_plate_text: str | None = None
    vehicle_color: str | None = None
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_year: str | None = None
    field_eval_candidate: bool = False

    _normalize_relative_path = field_validator("relative_path")(_validate_relative_path)

    @model_validator(mode="after")
    def validate_annotation_requirements(self) -> "DatasetAssetRecord":
        annotation_set = set(self.annotations)
        if AnnotationTask.plate_ocr in annotation_set and not self.expected_plate_text:
            raise ValueError("plate_ocr assets must include expected_plate_text")
        if AnnotationTask.vehicle_color in annotation_set and not self.vehicle_color:
            raise ValueError("vehicle_color assets must include vehicle_color")
        if AnnotationTask.vehicle_make in annotation_set and not self.vehicle_make:
            raise ValueError("vehicle_make assets must include vehicle_make")
        if AnnotationTask.vehicle_model in annotation_set and not self.vehicle_model:
            raise ValueError("vehicle_model assets must include vehicle_model")
        if AnnotationTask.vehicle_year in annotation_set and not self.vehicle_year:
            raise ValueError("vehicle_year assets must include vehicle_year")
        return self


class DatasetSplitSource(BaseModel):
    split: DatasetSplit
    relative_path: str = Field(..., min_length=1)
    label_path: str | None = None
    sample_count: int | None = Field(None, ge=0)
    capture_session_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    _normalize_relative_path = field_validator("relative_path")(_validate_relative_path)

    @field_validator("label_path")
    @classmethod
    def normalize_label_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_relative_path(value)


class TrainingDatasetManifest(BaseModel):
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    task: DatasetTask
    format: DatasetFormat
    storage_root: str = Field(..., min_length=1)
    review_status: DatasetReviewStatus = DatasetReviewStatus.pending
    provenance: DatasetProvenance
    annotation_review: AnnotationReview | None = None
    assets: list[DatasetAssetRecord] = Field(default_factory=list)
    splits: list[DatasetSplitSource] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("dataset_version", mode="before")
    @classmethod
    def normalize_dataset_version(cls, value):
        return _normalize_version(value)

    @model_validator(mode="after")
    def validate_manifest(self) -> "TrainingDatasetManifest":
        if not self.assets and not self.splits:
            raise ValueError("dataset manifest must define assets and/or splits")
        if self.review_status == DatasetReviewStatus.approved:
            if self.annotation_review is None:
                raise ValueError("approved dataset manifests require annotation_review")
            if not self.annotation_review.accepted_tasks:
                raise ValueError("approved dataset manifests require accepted_tasks in annotation_review")

        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("asset_id values must be unique within the manifest")

        asset_paths = [asset.relative_path for asset in self.assets]
        if len(asset_paths) != len(set(asset_paths)):
            raise ValueError("asset relative_path values must be unique within the manifest")

        split_keys = [(split.split, split.relative_path) for split in self.splits]
        if len(split_keys) != len(set(split_keys)):
            raise ValueError("split definitions must be unique by split name and relative_path")

        return self


class DatasetSplitAssignment(BaseModel):
    asset_id: str = Field(..., min_length=1)
    capture_session_id: str = Field(..., min_length=1)
    split: DatasetSplit
    relative_path: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)

    _normalize_relative_path = field_validator("relative_path")(_validate_relative_path)


class DatasetSplitManifest(BaseModel):
    split_name: str = Field(..., min_length=1)
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str | None = None
    source_manifest_path: str | None = None
    strategy: str = Field("capture_session_grouping", min_length=1)
    train_ratio: float = Field(..., ge=0.0, le=1.0)
    validation_ratio: float = Field(..., ge=0.0, le=1.0)
    holdout_ratio: float = Field(..., ge=0.0, le=1.0)
    field_eval_tags: list[str] = Field(default_factory=list)
    assignments: list[DatasetSplitAssignment] = Field(..., min_length=1)

    @field_validator("dataset_version", mode="before")
    @classmethod
    def normalize_dataset_version(cls, value):
        return _normalize_version(value)

    @model_validator(mode="after")
    def validate_ratios(self) -> "DatasetSplitManifest":
        total = self.train_ratio + self.validation_ratio + self.holdout_ratio
        if total <= 0.0:
            raise ValueError("train, validation, and holdout ratios must add up to more than zero")
        if total > 1.0:
            raise ValueError("train, validation, and holdout ratios must not exceed 1.0")
        return self
