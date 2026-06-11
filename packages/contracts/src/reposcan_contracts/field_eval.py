"""Field-eval qualification contracts for reviewed holdout datasets.

Covers two distinct concerns:

* ``FieldEvalQualificationReport`` — validates that a training dataset meets
  minimum coverage thresholds before it may be used as a holdout.
* ``FieldEvalHoldoutManifest`` — describes a registered regression holdout
  (night, long-range, etc.) and records acceptance thresholds for that scenario.
* ``FieldEvalReport`` — stores results of a completed field-eval run against a
  holdout manifest.  Fields are optional so reports can be created incrementally
  as each eval dimension is completed.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class FieldEvalScenario(str, Enum):
    """Named regression scenarios that holdout manifests are organised around."""

    night = "night"
    no_light = "no_light"
    ir_assisted = "ir_assisted"
    long_range = "long_range"
    glare = "glare"
    moving_vehicle = "moving_vehicle"
    moving_platform = "moving_platform"
    combined_night_long_range = "combined_night_long_range"


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


# ── Field-eval holdout manifest ───────────────────────────────────────────────


class FieldEvalAsset(BaseModel):
    """Single frame or clip in a field-eval holdout."""

    asset_id: str = Field(..., min_length=1)
    relative_path: str = Field(..., min_length=1, description="Path relative to holdout_root")
    expected_plate_text: str | None = None
    expected_vehicle_color: str | None = None
    expected_vehicle_make: str | None = None
    notes: str | None = None


class FieldEvalAcceptanceThresholds(BaseModel):
    """Minimum passing values for each eval dimension in this holdout scenario.

    Dimensions that are ``None`` are not enforced for this scenario —
    e.g. a moving-platform holdout may not require OCR exact-match.
    """

    min_exact_match_rate: float | None = Field(None, ge=0.0, le=1.0,
        description="Fraction of assets where OCR exactly matches expected plate text.")
    min_character_accuracy: float | None = Field(None, ge=0.0, le=1.0,
        description="Per-character accuracy across all plate reads.")
    max_average_latency_ms: float | None = Field(None, ge=0.0,
        description="Allowable average end-to-end inference latency per frame.")
    max_p95_latency_ms: float | None = Field(None, ge=0.0,
        description="Allowable 95th-percentile latency per frame.")
    min_detection_rate: float | None = Field(None, ge=0.0, le=1.0,
        description="Fraction of assets where at least one vehicle is detected.")
    min_plate_detection_rate: float | None = Field(None, ge=0.0, le=1.0,
        description="Fraction of assets where at least one plate is detected.")


class FieldEvalHoldoutManifest(BaseModel):
    """Registered regression holdout for a specific field-eval scenario.

    Loaded from ``data/datasets/field-eval-holdouts/<name>.yaml``.
    A holdout that has no assets yet is valid — it acts as a reserved slot
    until field data arrives.  The ``status`` field tracks readiness.
    """

    holdout_name: str = Field(..., min_length=1,
        description="Unique name for this holdout, e.g. 'night-long-range-v1'.")
    scenario: FieldEvalScenario
    description: str | None = None
    holdout_root: str = Field(..., min_length=1,
        description="Root directory for assets, relative to the repo root.")
    created_at_utc: UtcTimestamp
    last_updated_utc: UtcTimestamp | None = None
    status: str = Field("pending",
        pattern="^(pending|partial|ready|archived)$",
        description="pending=no data yet; partial=some data; ready=meets thresholds; archived=retired.")
    target_asset_count: int = Field(0, ge=0,
        description="Target number of assets for a fully populated holdout.")
    assets: list[FieldEvalAsset] = Field(default_factory=list)
    acceptance: FieldEvalAcceptanceThresholds = Field(
        default_factory=FieldEvalAcceptanceThresholds)
    notes: str | None = None


# ── Field-eval report ─────────────────────────────────────────────────────────


class FieldEvalDimensionResult(BaseModel):
    """Result for one evaluation dimension within a field-eval run."""

    dimension: str = Field(..., min_length=1,
        description="Name of the dimension, e.g. 'exact_match', 'character_accuracy'.")
    value: float | None = Field(None, description="Measured value (rate, ms, etc.).")
    threshold: float | None = Field(None, description="Acceptance threshold that was applied.")
    passed: bool | None = Field(None, description="True if value meets threshold; None if not evaluated.")
    sample_count: int = Field(0, ge=0)
    notes: str | None = None


class FieldEvalReport(BaseModel):
    """Results of a completed (or partial) field-eval run against a holdout manifest.

    Written by ``scripts/generate_field_eval_report.py`` and stored alongside
    the holdout manifest.  Optional fields allow partial reports when only some
    dimensions have been run.
    """

    holdout_name: str = Field(..., min_length=1)
    scenario: FieldEvalScenario
    model_stack_name: str = Field(..., min_length=1,
        description="Model stack identifier used for this eval run.")
    generated_at_utc: UtcTimestamp
    hardware_description: str | None = Field(None,
        description="e.g. 'Jetson AGX Orin 64 GB, JetPack 6.1, TensorRT 10.0.1'")
    total_assets_evaluated: int = Field(0, ge=0)
    dimensions: list[FieldEvalDimensionResult] = Field(default_factory=list)
    overall_passed: bool | None = Field(None,
        description="True only when all enforced dimensions pass their thresholds.")
    export_viable: bool | None = Field(None,
        description="True when the model output is suitable for evidence export handoff.")
    notes: str | None = None

    def passed_dimensions(self) -> list[FieldEvalDimensionResult]:
        return [d for d in self.dimensions if d.passed is True]

    def failed_dimensions(self) -> list[FieldEvalDimensionResult]:
        return [d for d in self.dimensions if d.passed is False]
