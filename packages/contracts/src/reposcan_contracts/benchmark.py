"""Benchmark manifest and report contracts for promoted-model evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class BenchmarkFrameExpectation(BaseModel):
    frame_path: str = Field(..., min_length=1)
    timestamp_utc: str | None = None
    expected_plate_text: str | None = None
    expected_vehicle_color: str | None = None
    expected_vehicle_make: str | None = None
    expected_vehicle_model: str | None = None
    expected_vehicle_year: str | None = None
    tags: list[str] = Field(default_factory=list)


class PromotedModelBenchmarkManifest(BaseModel):
    benchmark_name: str = Field(..., min_length=1)
    description: str | None = None
    camera_id: str = Field("cam_benchmark_01", min_length=1)
    frames: list[BenchmarkFrameExpectation] = Field(..., min_length=1)


class BenchmarkSubsetMetrics(BaseModel):
    frames: int = Field(..., ge=0)
    exact_match_rate: float | None = Field(None, ge=0.0, le=1.0)
    character_accuracy: float | None = Field(None, ge=0.0, le=1.0)
    color_accuracy: float | None = Field(None, ge=0.0, le=1.0)
    make_accuracy: float | None = Field(None, ge=0.0, le=1.0)
    average_latency_ms: float | None = Field(None, ge=0.0)
    p95_latency_ms: float | None = Field(None, ge=0.0)
    max_latency_ms: float | None = Field(None, ge=0.0)
    average_vehicles_per_frame: float | None = Field(None, ge=0.0)
    average_plates_per_frame: float | None = Field(None, ge=0.0)


class BenchmarkValidationSummary(BaseModel):
    runtime_ready: bool
    promotion_ready: bool
    deployment_ready: bool | None = None
    deployment_name: str | None = None
    issues: list[str] = Field(default_factory=list)


class PromotedModelBenchmarkReport(BaseModel):
    benchmark_name: str = Field(..., min_length=1)
    model_stack_name: str = Field(..., min_length=1)
    generated_at_utc: UtcTimestamp
    benchmark_manifest_path: str | None = None
    source_dataset_name: str | None = None
    source_dataset_version: str | None = None
    source_dataset_manifest_path: str | None = None
    overall: BenchmarkSubsetMetrics
    subsets: dict[str, BenchmarkSubsetMetrics] = Field(default_factory=dict)
    validation: BenchmarkValidationSummary | None = None
