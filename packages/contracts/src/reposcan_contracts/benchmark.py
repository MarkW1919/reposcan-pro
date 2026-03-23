"""Benchmark manifest contracts for promoted-model evaluation scaffolding."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
