from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcan_contracts.dataset import DatasetFormat, DatasetReviewStatus, DistanceBand, LightingCondition, TrainingDatasetManifest
from reposcan_contracts.field_eval import (
    FieldEvalCoveragePolicy,
    FieldEvalQualificationIssue,
    FieldEvalQualificationReport,
    FieldEvalSubsetSummary,
)

from .workflows import resolve_storage_root

_LOW_LIGHT_CONDITIONS = {
    LightingCondition.dusk,
    LightingCondition.night,
    LightingCondition.no_light,
    LightingCondition.ir_assisted,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_long_range(asset) -> bool:
    return asset.distance_band == DistanceBand.long_range or "long_range" in asset.tags


def _is_low_light(asset) -> bool:
    return "low_light" in asset.tags or any(condition in _LOW_LIGHT_CONDITIONS for condition in asset.lighting_conditions)


def _is_benchmark_ready(asset, *, require_expected_plate_text: bool) -> bool:
    if not require_expected_plate_text:
        return any(
            [
                asset.expected_plate_text,
                asset.vehicle_color,
                asset.vehicle_make,
                asset.vehicle_model,
                asset.vehicle_year,
            ]
        )
    return bool(asset.expected_plate_text)


def _subset_summary(assets, *, require_expected_plate_text: bool) -> FieldEvalSubsetSummary:
    return FieldEvalSubsetSummary(
        assets=len(assets),
        benchmark_ready_assets=sum(
            1 for asset in assets if _is_benchmark_ready(asset, require_expected_plate_text=require_expected_plate_text)
        ),
        capture_sessions=sorted({asset.capture_session_id for asset in assets}),
    )


def qualify_field_eval_dataset(
    *,
    repo_root: Path,
    manifest: TrainingDatasetManifest,
    policy: FieldEvalCoveragePolicy | None = None,
) -> FieldEvalQualificationReport:
    active_policy = policy or FieldEvalCoveragePolicy()
    issues: list[FieldEvalQualificationIssue] = []

    if manifest.format != DatasetFormat.eval_holdout:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="dataset",
                message="field-eval qualification requires a dataset manifest with format=eval_holdout",
            )
        )

    if active_policy.require_approved_review and manifest.review_status != DatasetReviewStatus.approved:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="dataset",
                message="field-eval qualification requires an approved eval-holdout dataset manifest",
            )
        )

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    missing_file_assets = 0
    missing_expected_plate_assets = 0
    benchmark_ready_assets = 0

    for asset in manifest.assets:
        if active_policy.verify_files and not (storage_root / asset.relative_path).exists():
            missing_file_assets += 1
        if _is_benchmark_ready(asset, require_expected_plate_text=active_policy.require_expected_plate_text):
            benchmark_ready_assets += 1
        else:
            missing_expected_plate_assets += 1

    if active_policy.verify_files and missing_file_assets:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="files",
                message=f"{missing_file_assets} field-eval assets are missing from storage_root '{storage_root}'",
            )
        )

    if missing_expected_plate_assets:
        issues.append(
            FieldEvalQualificationIssue(
                severity="warning",
                scope="labels",
                message=(
                    f"{missing_expected_plate_assets} assets are missing expected plate text and will not contribute "
                    "to exact-match or character-accuracy reporting"
                ),
            )
        )

    total_assets = len(manifest.assets)
    total_sessions = len({asset.capture_session_id for asset in manifest.assets})
    long_range_assets = [asset for asset in manifest.assets if _is_long_range(asset)]
    low_light_assets = [asset for asset in manifest.assets if _is_low_light(asset)]

    subsets = {
        "long_range": _subset_summary(long_range_assets, require_expected_plate_text=active_policy.require_expected_plate_text),
        "low_light": _subset_summary(low_light_assets, require_expected_plate_text=active_policy.require_expected_plate_text),
    }

    if total_assets < active_policy.min_total_assets:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="coverage",
                message=f"total assets {total_assets} is below required minimum {active_policy.min_total_assets}",
            )
        )

    if benchmark_ready_assets < active_policy.min_benchmark_ready_assets:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="coverage",
                message=(
                    f"benchmark-ready assets {benchmark_ready_assets} is below required minimum "
                    f"{active_policy.min_benchmark_ready_assets}"
                ),
            )
        )

    if subsets["long_range"].assets < active_policy.min_long_range_assets:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="long_range",
                message=(
                    f"long_range assets {subsets['long_range'].assets} is below required minimum "
                    f"{active_policy.min_long_range_assets}"
                ),
            )
        )

    if len(subsets["long_range"].capture_sessions) < active_policy.min_long_range_sessions:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="long_range",
                message=(
                    f"long_range capture sessions {len(subsets['long_range'].capture_sessions)} is below required minimum "
                    f"{active_policy.min_long_range_sessions}"
                ),
            )
        )

    if subsets["low_light"].assets < active_policy.min_low_light_assets:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="low_light",
                message=(
                    f"low_light assets {subsets['low_light'].assets} is below required minimum "
                    f"{active_policy.min_low_light_assets}"
                ),
            )
        )

    if len(subsets["low_light"].capture_sessions) < active_policy.min_low_light_sessions:
        issues.append(
            FieldEvalQualificationIssue(
                severity="error",
                scope="low_light",
                message=(
                    f"low_light capture sessions {len(subsets['low_light'].capture_sessions)} is below required minimum "
                    f"{active_policy.min_low_light_sessions}"
                ),
            )
        )

    return FieldEvalQualificationReport(
        dataset_name=manifest.dataset_name,
        dataset_version=manifest.dataset_version,
        generated_at_utc=_utcnow(),
        qualified=not any(issue.severity == "error" for issue in issues),
        total_assets=total_assets,
        benchmark_ready_assets=benchmark_ready_assets,
        missing_expected_plate_assets=missing_expected_plate_assets,
        missing_file_assets=missing_file_assets,
        total_capture_sessions=total_sessions,
        policy=active_policy,
        subsets=subsets,
        issues=issues,
    )
