"""Field-eval qualification contracts for reviewed holdout datasets."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class FieldEvalCoveragePolicy(BaseModel):
    min_total_assets: int = Field(10, ge=1)
    min_benchmark_ready_assets: int = Field(10, ge=1)
    min_long_range_assets: int = Field(4, ge=0)
    min_low_light_assets: int = Field(4, ge=0)
    min_long_range_sessions: int = Field(2, ge=0)
    min_low_light_sessions: int = Field(2, ge=0)
    require_expected_plate_text: bool = True
    require_approved_review: bool = True
    verify_files: bool = False


class FieldEvalSubsetSummary(BaseModel):
    assets: int = Field(..., ge=0)
    benchmark_ready_assets: int = Field(..., ge=0)
    capture_sessions: list[str] = Field(default_factory=list)


class FieldEvalQualificationIssue(BaseModel):
    severity: str = Field(pattern="^(error|warning)$")
    scope: str
    message: str


class FieldEvalQualificationReport(BaseModel):
    dataset_name: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    generated_at_utc: UtcTimestamp
    qualified: bool
    total_assets: int = Field(..., ge=0)
    benchmark_ready_assets: int = Field(..., ge=0)
    missing_expected_plate_assets: int = Field(0, ge=0)
    missing_file_assets: int = Field(0, ge=0)
    total_capture_sessions: int = Field(..., ge=0)
    policy: FieldEvalCoveragePolicy
    subsets: dict[str, FieldEvalSubsetSummary] = Field(default_factory=dict)
    issues: list[FieldEvalQualificationIssue] = Field(default_factory=list)
