"""Dataset production-readiness contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .dataset import DatasetLicenseTier, DatasetTask


class DatasetReadinessThresholds(BaseModel):
    min_total_samples: int = Field(0, ge=0)
    min_train_samples: int = Field(0, ge=0)
    min_validation_samples: int = Field(0, ge=0)
    min_holdout_samples: int = Field(0, ge=0)
    min_field_eval_samples: int = Field(0, ge=0)
    min_capture_sessions: int = Field(0, ge=0)
    min_low_light_assets: int = Field(0, ge=0)
    min_long_range_assets: int = Field(0, ge=0)
    max_synthetic_train_fraction: float = Field(0.25, ge=0.0, le=1.0)


class DatasetReadinessPolicy(BaseModel):
    policy_name: str = Field(..., min_length=1)
    require_approved_review: bool = True
    require_license_review: bool = True
    require_annotation_review: bool = True
    require_capture_session_metadata: bool = True
    require_condition_metadata: bool = True
    verify_files: bool = False
    allowed_license_tiers: list[DatasetLicenseTier] = Field(
        default_factory=lambda: [
            DatasetLicenseTier.internal,
            DatasetLicenseTier.public,
            DatasetLicenseTier.commercial,
            DatasetLicenseTier.restricted,
        ]
    )
    thresholds_by_task: dict[DatasetTask, DatasetReadinessThresholds] = Field(default_factory=dict)
    required_asset_tag_samples: dict[str, int] = Field(default_factory=dict)


class DatasetReadinessIssue(BaseModel):
    severity: str = Field(..., pattern="^(error|warning)$")
    scope: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class DatasetReadinessLabelSummary(BaseModel):
    expected_annotation_tasks: list[str] = Field(default_factory=list)
    assets_with_expected_annotations: int = Field(0, ge=0)
    assets_missing_expected_annotations: int = Field(0, ge=0)
    split_label_paths: int = Field(0, ge=0)


class DatasetReadinessReport(BaseModel):
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    task: DatasetTask
    generated_at_utc: str = Field(..., min_length=1)
    ready: bool
    policy_name: str = Field(..., min_length=1)
    storage_root: str = Field(..., min_length=1)
    total_samples: int = Field(0, ge=0)
    total_assets: int = Field(0, ge=0)
    split_samples: dict[str, int] = Field(default_factory=dict)
    capture_sessions: int = Field(0, ge=0)
    low_light_assets: int = Field(0, ge=0)
    long_range_assets: int = Field(0, ge=0)
    synthetic_train_samples: int = Field(0, ge=0)
    missing_files: int = Field(0, ge=0)
    asset_tag_counts: dict[str, int] = Field(default_factory=dict)
    label_summary: DatasetReadinessLabelSummary
    thresholds: DatasetReadinessThresholds
    issues: list[DatasetReadinessIssue] = Field(default_factory=list)
