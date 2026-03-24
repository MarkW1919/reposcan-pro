"""Tracking benchmark report contracts for strategy comparison and suppression tuning."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .config.pipeline import TrackingAlgorithm
from .types import UtcTimestamp


class TrackingScenarioMetrics(BaseModel):
    frames: int = Field(..., ge=0)
    expected_objects: int = Field(..., ge=0)
    finalized_detections: int = Field(..., ge=0)
    expected_finalized_detections: int = Field(..., ge=0)
    plate_exact_matches: int = Field(..., ge=0)
    identity_switches: int = Field(..., ge=0)
    suppressed_duplicates: int = Field(..., ge=0)
    score: float


class TrackingAlgorithmBenchmark(BaseModel):
    algorithm: TrackingAlgorithm
    scenarios: dict[str, TrackingScenarioMetrics] = Field(default_factory=dict)
    total_score: float


class TrackingStrategyBenchmarkReport(BaseModel):
    benchmark_name: str = Field(..., min_length=1)
    generated_at_utc: UtcTimestamp
    recommended_algorithm: TrackingAlgorithm
    algorithms: dict[str, TrackingAlgorithmBenchmark] = Field(default_factory=dict)
