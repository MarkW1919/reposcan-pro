"""Training profile and prepared-run contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .dataset import DatasetTask
from .types import UtcTimestamp


class TrainingFramework(str, Enum):
    ultralytics = "ultralytics"
    torchvision = "torchvision"
    paddleocr = "paddleocr"


class DatasetAdapter(str, Enum):
    imagefolder = "imagefolder"
    stanford_cars = "stanford_cars"
    manifest_split = "manifest_split"


class AugmentationPolicy(BaseModel):
    motion_blur: bool = True
    defocus_blur: bool = True
    brightness_contrast: bool = True
    noise: bool = True
    compression_artifacts: bool = True
    perspective_distortion: bool = True
    synthetic_support_ratio: float = Field(0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class TrainingProfileConfig(BaseModel):
    profile_name: str = Field(..., min_length=1)
    task: DatasetTask
    framework: TrainingFramework
    output_root: str = Field("runtime/training", min_length=1)
    allow_pending_review: bool = False
    dataset_adapter: DatasetAdapter = DatasetAdapter.manifest_split
    base_model: str | None = None
    image_size: int = Field(640, gt=0)
    epochs: int = Field(50, gt=0)
    batch_size: int = Field(16, gt=0)
    workers: int = Field(4, ge=0)
    patience: int = Field(10, ge=0)
    seed: int = 42
    precision: str = Field("fp32", min_length=1)
    device: str = Field("auto", min_length=1)
    class_names: list[str] = Field(default_factory=list)
    use_amp: bool = True
    augmentation: AugmentationPolicy = Field(default_factory=AugmentationPolicy)

    @model_validator(mode="after")
    def validate_framework_task_compatibility(self) -> "TrainingProfileConfig":
        classification_tasks = {
            DatasetTask.vehicle_color_classification,
            DatasetTask.vehicle_make_model_classification,
            DatasetTask.vehicle_year_classification,
        }
        detection_tasks = {
            DatasetTask.vehicle_detection,
            DatasetTask.plate_detection,
        }

        if self.task in classification_tasks and self.framework != TrainingFramework.torchvision:
            raise ValueError("classification tasks require framework=torchvision")
        if self.task in detection_tasks and self.framework != TrainingFramework.ultralytics:
            raise ValueError("detection tasks require framework=ultralytics")
        if self.task == DatasetTask.plate_ocr and self.framework != TrainingFramework.paddleocr:
            raise ValueError("plate_ocr requires framework=paddleocr")

        if self.task in detection_tasks and not self.class_names:
            raise ValueError("detection profiles require at least one class_name")

        if self.task == DatasetTask.vehicle_make_model_classification and self.dataset_adapter == DatasetAdapter.manifest_split:
            raise ValueError("vehicle_make_model_classification requires a dataset_adapter such as stanford_cars or imagefolder")

        return self


class TrainingRunManifest(BaseModel):
    run_name: str = Field(..., min_length=1)
    profile_name: str = Field(..., min_length=1)
    task: DatasetTask
    framework: TrainingFramework
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    dataset_manifest_path: str = Field(..., min_length=1)
    prepared_at_utc: UtcTimestamp
    workspace_dir: str = Field(..., min_length=1)
    prepared_files: list[str] = Field(default_factory=list)
    training_command: list[str] = Field(default_factory=list)
    export_command: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
