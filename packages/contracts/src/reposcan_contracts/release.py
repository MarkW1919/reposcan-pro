"""Promotion-release registry contracts for accepted model bundles."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class ReleaseChannelAction(str, Enum):
    promote = "promote"
    rollback = "rollback"


class ReleaseBenchmarkSummary(BaseModel):
    frames: int = Field(..., ge=0)
    exact_match_rate: float | None = Field(None, ge=0.0, le=1.0)
    character_accuracy: float | None = Field(None, ge=0.0, le=1.0)
    color_accuracy: float | None = Field(None, ge=0.0, le=1.0)
    make_accuracy: float | None = Field(None, ge=0.0, le=1.0)


class ReleaseValidationSummary(BaseModel):
    runtime_ready: bool
    promotion_ready: bool
    deployment_ready: bool
    error_count: int = Field(0, ge=0)
    warning_count: int = Field(0, ge=0)
    issues: list[str] = Field(default_factory=list)


class ModelReleaseRecord(BaseModel):
    release_id: str = Field(..., min_length=1)
    channel_name: str = Field(..., min_length=1)
    released_at_utc: UtcTimestamp
    stack_name: str = Field(..., min_length=1)
    bundle_root: str = Field(..., min_length=1)
    model_config_path: str = Field(..., min_length=1)
    deployment_config_path: str = Field(..., min_length=1)
    benchmark_manifest_path: str = Field(..., min_length=1)
    benchmark_report_path: str = Field(..., min_length=1)
    benchmark_name: str = Field(..., min_length=1)
    overall_benchmark: ReleaseBenchmarkSummary
    subset_benchmarks: dict[str, ReleaseBenchmarkSummary] = Field(default_factory=dict)
    validation: ReleaseValidationSummary
    source_run_ids: list[str] = Field(default_factory=list)
    source_checkpoint_refs: list[str] = Field(default_factory=list)
    dataset_manifest_refs: list[str] = Field(default_factory=list)
    supersedes_release_id: str | None = None
    notes: str | None = None


class ReleaseChannelEvent(BaseModel):
    occurred_at_utc: UtcTimestamp
    action: ReleaseChannelAction
    release_id: str = Field(..., min_length=1)
    previous_release_id: str | None = None
    notes: str | None = None


class ModelReleaseChannel(BaseModel):
    channel_name: str = Field(..., min_length=1)
    current_release_id: str = Field(..., min_length=1)
    previous_release_id: str | None = None
    updated_at_utc: UtcTimestamp
    release_history: list[str] = Field(default_factory=list)
    events: list[ReleaseChannelEvent] = Field(default_factory=list)
    notes: str | None = None
