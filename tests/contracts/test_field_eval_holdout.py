"""Tests for FieldEvalHoldoutManifest, FieldEvalReport, and related contracts.

Covers:
1. All three seed holdout manifests parse and validate cleanly.
2. FieldEvalHoldoutManifest schema enforces required fields and enum values.
3. FieldEvalReport can be built programmatically and passes schema validation.
4. FieldEvalReport.passed_dimensions / failed_dimensions helpers work correctly.
5. loader.load_field_eval_holdout_manifest raises ConfigLoadError on bad input.
6. Acceptance thresholds default to None (unenforced) when not specified.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from reposcan_contracts.config.loader import (
    ConfigLoadError,
    load_field_eval_holdout_manifest,
    load_field_eval_report,
)
from reposcan_contracts.field_eval import (
    FieldEvalAcceptanceThresholds,
    FieldEvalAsset,
    FieldEvalDimensionResult,
    FieldEvalHoldoutManifest,
    FieldEvalReport,
    FieldEvalScenario,
)


DATA_ROOT = Path(__file__).parent.parent.parent / "configs" / "datasets" / "holdouts"
HOLDOUT_FILES = [
    DATA_ROOT / "night-v1.yaml",
    DATA_ROOT / "long-range-v1.yaml",
    DATA_ROOT / "combined-night-long-range-v1.yaml",
]


# ── Seed manifest loading ─────────────────────────────────────────────────────

class TestSeedHoldoutManifests:
    @pytest.mark.parametrize("path", HOLDOUT_FILES, ids=lambda p: p.stem)
    def test_manifest_parses(self, path: Path):
        manifest = load_field_eval_holdout_manifest(path)
        assert manifest.holdout_name
        assert manifest.scenario in FieldEvalScenario.__members__.values()
        assert manifest.status in ("pending", "partial", "ready", "archived")
        assert manifest.holdout_root.endswith("/")

    def test_night_manifest_fields(self):
        manifest = load_field_eval_holdout_manifest(DATA_ROOT / "night-v1.yaml")
        assert manifest.scenario == FieldEvalScenario.night
        assert manifest.status == "pending"
        assert manifest.target_asset_count > 0
        assert manifest.acceptance.min_exact_match_rate is not None
        assert manifest.acceptance.min_exact_match_rate < 0.85, (
            "Night exact-match threshold must be below daylight target"
        )

    def test_long_range_manifest_fields(self):
        manifest = load_field_eval_holdout_manifest(DATA_ROOT / "long-range-v1.yaml")
        assert manifest.scenario == FieldEvalScenario.long_range
        assert manifest.acceptance.min_plate_detection_rate is not None
        assert manifest.acceptance.min_plate_detection_rate < 0.80, (
            "Long-range plate detection threshold must be below daylight target"
        )

    def test_combined_manifest_is_strictest_hardware_only(self):
        combined = load_field_eval_holdout_manifest(DATA_ROOT / "combined-night-long-range-v1.yaml")
        night = load_field_eval_holdout_manifest(DATA_ROOT / "night-v1.yaml")
        # Combined worst-case thresholds must be <= night-only thresholds
        assert combined.acceptance.min_exact_match_rate <= night.acceptance.min_exact_match_rate

    def test_pending_manifest_allows_empty_assets(self):
        manifest = load_field_eval_holdout_manifest(DATA_ROOT / "night-v1.yaml")
        assert manifest.assets == []


# ── Schema construction ───────────────────────────────────────────────────────

class TestFieldEvalHoldoutManifestSchema:
    def _minimal_manifest(self, **overrides) -> dict:
        base = {
            "holdout_name": "test-holdout-v1",
            "scenario": "night",
            "holdout_root": "data/datasets/field-eval-holdouts/test/",
            "created_at_utc": "2026-03-30T00:00:00Z",
            "status": "pending",
            "target_asset_count": 10,
        }
        base.update(overrides)
        return base

    def test_minimal_valid_manifest(self):
        m = FieldEvalHoldoutManifest.model_validate(self._minimal_manifest())
        assert m.holdout_name == "test-holdout-v1"
        assert m.assets == []
        assert m.acceptance.min_exact_match_rate is None

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            FieldEvalHoldoutManifest.model_validate(
                self._minimal_manifest(status="unknown_status")
            )

    def test_invalid_scenario_rejected(self):
        with pytest.raises(ValidationError):
            FieldEvalHoldoutManifest.model_validate(
                self._minimal_manifest(scenario="underwater")
            )

    def test_asset_record_validates(self):
        asset = FieldEvalAsset(
            asset_id="asset_001",
            relative_path="frames/img001.jpg",
            expected_plate_text="ABC123",
        )
        assert asset.expected_plate_text == "ABC123"

    def test_acceptance_thresholds_defaults_to_none(self):
        thresholds = FieldEvalAcceptanceThresholds()
        assert thresholds.min_exact_match_rate is None
        assert thresholds.max_average_latency_ms is None

    def test_acceptance_threshold_bounds(self):
        with pytest.raises(ValidationError):
            FieldEvalAcceptanceThresholds(min_exact_match_rate=1.5)
        with pytest.raises(ValidationError):
            FieldEvalAcceptanceThresholds(min_exact_match_rate=-0.1)

    def test_all_scenarios_are_valid(self):
        for scenario in FieldEvalScenario:
            m = FieldEvalHoldoutManifest.model_validate(
                self._minimal_manifest(scenario=scenario.value)
            )
            assert m.scenario == scenario


# ── FieldEvalReport schema ────────────────────────────────────────────────────

class TestFieldEvalReport:
    def _sample_report(self, **overrides) -> FieldEvalReport:
        base = {
            "holdout_name": "night-v1",
            "scenario": "night",
            "model_stack_name": "reposcan-edge-v0.1.0",
            "generated_at_utc": "2026-03-30T12:00:00Z",
            "total_assets_evaluated": 0,
            "dimensions": [],
            "overall_passed": None,
        }
        base.update(overrides)
        return FieldEvalReport.model_validate(base)

    def test_empty_report_validates(self):
        report = self._sample_report()
        assert report.total_assets_evaluated == 0
        assert report.overall_passed is None
        assert report.dimensions == []

    def test_report_with_dimensions(self):
        dimensions = [
            {
                "dimension": "exact_match",
                "value": 0.72,
                "threshold": 0.70,
                "passed": True,
                "sample_count": 40,
            },
            {
                "dimension": "character_accuracy",
                "value": 0.81,
                "threshold": 0.85,
                "passed": False,
                "sample_count": 40,
            },
        ]
        report = self._sample_report(
            total_assets_evaluated=40,
            dimensions=dimensions,
            overall_passed=False,
        )
        assert len(report.passed_dimensions()) == 1
        assert len(report.failed_dimensions()) == 1
        assert report.passed_dimensions()[0].dimension == "exact_match"
        assert report.failed_dimensions()[0].dimension == "character_accuracy"

    def test_passed_report(self):
        dims = [
            FieldEvalDimensionResult(
                dimension="exact_match", value=0.75, threshold=0.70,
                passed=True, sample_count=50,
            ),
            FieldEvalDimensionResult(
                dimension="character_accuracy", value=0.88, threshold=0.85,
                passed=True, sample_count=50,
            ),
        ]
        report = FieldEvalReport(
            holdout_name="night-v1",
            scenario=FieldEvalScenario.night,
            model_stack_name="reposcan-edge-v0.1.0",
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            total_assets_evaluated=50,
            dimensions=dims,
            overall_passed=True,
            export_viable=True,
        )
        assert report.overall_passed is True
        assert report.failed_dimensions() == []

    def test_dimension_without_threshold_has_none_passed(self):
        dim = FieldEvalDimensionResult(
            dimension="export_viability",
            value=None,
            threshold=None,
            passed=None,
            sample_count=0,
        )
        report = self._sample_report(
            dimensions=[dim.model_dump()],
            total_assets_evaluated=0,
        )
        assert report.dimensions[0].passed is None

    def test_report_scenario_enum_round_trips(self):
        for scenario in FieldEvalScenario:
            report = self._sample_report(scenario=scenario.value)
            assert report.scenario == scenario


# ── Loader error handling ─────────────────────────────────────────────────────

class TestLoaderErrors:
    def test_missing_file_raises_config_load_error(self, tmp_path: Path):
        with pytest.raises(ConfigLoadError, match="file not found"):
            load_field_eval_holdout_manifest(tmp_path / "does_not_exist.yaml")

    def test_invalid_yaml_raises_config_load_error(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("holdout_name: [unclosed", encoding="utf-8")
        with pytest.raises(ConfigLoadError, match="YAML parse error"):
            load_field_eval_holdout_manifest(bad)

    def test_missing_required_fields_raises_config_load_error(self, tmp_path: Path):
        incomplete = tmp_path / "incomplete.yaml"
        incomplete.write_text("holdout_name: only-this-field\n", encoding="utf-8")
        with pytest.raises(ConfigLoadError):
            load_field_eval_holdout_manifest(incomplete)
