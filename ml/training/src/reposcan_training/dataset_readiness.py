from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from reposcan_contracts.dataset import (
    AnnotationTask,
    DatasetFormat,
    DatasetLicenseTier,
    DatasetReviewStatus,
    DatasetSourceKind,
    DatasetSplit,
    DatasetTask,
    DistanceBand,
    LightingCondition,
    TrainingDatasetManifest,
)
from reposcan_contracts.dataset_readiness import (
    DatasetReadinessIssue,
    DatasetReadinessLabelSummary,
    DatasetReadinessPolicy,
    DatasetReadinessReport,
    DatasetReadinessThresholds,
)

from .workflows import resolve_storage_root

_LOW_LIGHT_CONDITIONS = {
    LightingCondition.dusk,
    LightingCondition.night,
    LightingCondition.no_light,
    LightingCondition.ir_assisted,
    LightingCondition.glare,
}

_EXPECTED_ANNOTATIONS_BY_TASK = {
    DatasetTask.vehicle_detection: [AnnotationTask.vehicle_detection],
    DatasetTask.plate_detection: [AnnotationTask.plate_detection],
    DatasetTask.plate_ocr: [AnnotationTask.plate_ocr],
    DatasetTask.vehicle_color_classification: [AnnotationTask.vehicle_color],
    DatasetTask.vehicle_make_model_classification: [AnnotationTask.vehicle_make, AnnotationTask.vehicle_model],
    DatasetTask.vehicle_year_classification: [AnnotationTask.vehicle_year],
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_dataset_readiness_policy(level: str = "oklahoma-commercial") -> DatasetReadinessPolicy:
    """Return a dataset gate for the requested shipping level.

    The Oklahoma commercial profile is intentionally strict: it is a release gate,
    not a convenience validator for small fixtures or warm-start experiments.
    """

    normalized = level.strip().lower().replace("_", "-")
    if normalized in {"warmstart", "public-warmstart", "benchmark-warmstart"}:
        thresholds = DatasetReadinessThresholds(
            min_total_samples=50,
            min_train_samples=30,
            min_validation_samples=10,
            min_holdout_samples=0,
            min_field_eval_samples=0,
            min_capture_sessions=1,
            min_low_light_assets=0,
            min_long_range_assets=0,
            max_synthetic_train_fraction=0.5,
        )
        return DatasetReadinessPolicy(
            policy_name="warmstart",
            require_approved_review=False,
            require_license_review=False,
            require_annotation_review=False,
            require_capture_session_metadata=False,
            require_condition_metadata=False,
            thresholds_by_task={task: thresholds for task in DatasetTask},
        )

    if normalized in {"dev", "development"}:
        thresholds = DatasetReadinessThresholds(
            min_total_samples=10,
            min_train_samples=5,
            min_validation_samples=2,
            min_holdout_samples=2,
            min_field_eval_samples=5,
            min_capture_sessions=2,
            min_low_light_assets=1,
            min_long_range_assets=1,
            max_synthetic_train_fraction=0.5,
        )
        return DatasetReadinessPolicy(
            policy_name="development",
            require_approved_review=True,
            require_license_review=False,
            require_capture_session_metadata=False,
            require_condition_metadata=False,
            thresholds_by_task={task: thresholds for task in DatasetTask},
        )

    if normalized in {"production", "production-candidate"}:
        return DatasetReadinessPolicy(
            policy_name="production-candidate",
            thresholds_by_task={
                DatasetTask.vehicle_detection: DatasetReadinessThresholds(
                    min_total_samples=10000,
                    min_train_samples=7000,
                    min_validation_samples=1000,
                    min_holdout_samples=1500,
                    min_field_eval_samples=500,
                    min_capture_sessions=25,
                    min_low_light_assets=1000,
                    min_long_range_assets=1000,
                ),
                DatasetTask.plate_detection: DatasetReadinessThresholds(
                    min_total_samples=10000,
                    min_train_samples=7000,
                    min_validation_samples=1000,
                    min_holdout_samples=1500,
                    min_field_eval_samples=500,
                    min_capture_sessions=25,
                    min_low_light_assets=1000,
                    min_long_range_assets=1000,
                ),
                DatasetTask.plate_ocr: DatasetReadinessThresholds(
                    min_total_samples=25000,
                    min_train_samples=18000,
                    min_validation_samples=2500,
                    min_holdout_samples=2500,
                    min_capture_sessions=25,
                    min_low_light_assets=1000,
                    min_long_range_assets=500,
                    max_synthetic_train_fraction=0.25,
                ),
                DatasetTask.vehicle_color_classification: DatasetReadinessThresholds(
                    min_total_samples=20000,
                    min_train_samples=14000,
                    min_validation_samples=2000,
                    min_holdout_samples=3000,
                    min_capture_sessions=25,
                    min_low_light_assets=2000,
                    min_long_range_assets=1000,
                ),
                DatasetTask.vehicle_make_model_classification: DatasetReadinessThresholds(
                    min_total_samples=50000,
                    min_train_samples=35000,
                    min_validation_samples=5000,
                    min_holdout_samples=7500,
                    min_capture_sessions=50,
                    min_low_light_assets=2500,
                    min_long_range_assets=1500,
                ),
                DatasetTask.vehicle_year_classification: DatasetReadinessThresholds(
                    min_total_samples=50000,
                    min_train_samples=35000,
                    min_validation_samples=5000,
                    min_holdout_samples=7500,
                    min_capture_sessions=50,
                    min_low_light_assets=2500,
                    min_long_range_assets=1500,
                ),
            },
        )

    if normalized not in {"commercial", "commercial-grade", "oklahoma-commercial"}:
        raise ValueError(
            "readiness level must be one of: development, production-candidate, commercial-grade, oklahoma-commercial"
        )

    return DatasetReadinessPolicy(
        policy_name="oklahoma-commercial",
        thresholds_by_task={
            DatasetTask.vehicle_detection: DatasetReadinessThresholds(
                min_total_samples=50000,
                min_train_samples=35000,
                min_validation_samples=5000,
                min_holdout_samples=7500,
                min_field_eval_samples=2500,
                min_capture_sessions=75,
                min_low_light_assets=5000,
                min_long_range_assets=5000,
            ),
            DatasetTask.plate_detection: DatasetReadinessThresholds(
                min_total_samples=50000,
                min_train_samples=35000,
                min_validation_samples=5000,
                min_holdout_samples=7500,
                min_field_eval_samples=2500,
                min_capture_sessions=75,
                min_low_light_assets=5000,
                min_long_range_assets=5000,
            ),
            DatasetTask.plate_ocr: DatasetReadinessThresholds(
                min_total_samples=100000,
                min_train_samples=75000,
                min_validation_samples=10000,
                min_holdout_samples=10000,
                min_capture_sessions=75,
                min_low_light_assets=5000,
                min_long_range_assets=2500,
                max_synthetic_train_fraction=0.20,
            ),
            DatasetTask.vehicle_color_classification: DatasetReadinessThresholds(
                min_total_samples=75000,
                min_train_samples=50000,
                min_validation_samples=7500,
                min_holdout_samples=10000,
                min_capture_sessions=75,
                min_low_light_assets=10000,
                min_long_range_assets=5000,
            ),
            DatasetTask.vehicle_make_model_classification: DatasetReadinessThresholds(
                min_total_samples=150000,
                min_train_samples=100000,
                min_validation_samples=15000,
                min_holdout_samples=20000,
                min_capture_sessions=100,
                min_low_light_assets=10000,
                min_long_range_assets=5000,
            ),
            DatasetTask.vehicle_year_classification: DatasetReadinessThresholds(
                min_total_samples=150000,
                min_train_samples=100000,
                min_validation_samples=15000,
                min_holdout_samples=20000,
                min_capture_sessions=100,
                min_low_light_assets=10000,
                min_long_range_assets=5000,
            ),
        },
        required_asset_tag_samples={
            "vehicle_class:pickup": 10000,
            "vehicle_class:suv_crossover": 12000,
            "vehicle_class:passenger_car": 8000,
            "vehicle_class:van_minivan": 1500,
            "make_model:ford_f_series": 2500,
            "make_model:chevrolet_silverado": 2000,
            "make_model:ram_pickup": 1500,
            "make_model:gmc_sierra": 1000,
            "make_model:toyota_tacoma": 750,
            "make_model:chevrolet_tahoe_suburban": 750,
        },
    )


def _split_samples(manifest: TrainingDatasetManifest) -> dict[str, int]:
    samples: dict[str, int] = {}
    for split in manifest.splits:
        samples[split.split.value] = samples.get(split.split.value, 0) + (split.sample_count or 0)
    return samples


def _total_samples(manifest: TrainingDatasetManifest, split_samples: dict[str, int]) -> int:
    if split_samples:
        return sum(split_samples.values())
    return len(manifest.assets)


def _assets_for_split(manifest: TrainingDatasetManifest, split: DatasetSplit) -> list:
    split_paths = [item.relative_path.rstrip("/") + "/" for item in manifest.splits if item.split == split]
    if not split_paths:
        return []
    return [asset for asset in manifest.assets if any(asset.relative_path.startswith(path) for path in split_paths)]


def _synthetic_train_samples(manifest: TrainingDatasetManifest, split_samples: dict[str, int]) -> int:
    if manifest.provenance.source_kind == DatasetSourceKind.synthetic:
        if DatasetSplit.train.value in split_samples:
            return split_samples[DatasetSplit.train.value]
        return len(_assets_for_split(manifest, DatasetSplit.train)) or len(manifest.assets)

    total = 0
    for split in manifest.splits:
        if split.split == DatasetSplit.train and "synthetic" in split.tags:
            total += split.sample_count or 0
    for asset in _assets_for_split(manifest, DatasetSplit.train):
        if "synthetic" in asset.tags:
            total += 1
    return total


def _is_low_light(asset) -> bool:
    return "low_light" in asset.tags or any(condition in _LOW_LIGHT_CONDITIONS for condition in asset.lighting_conditions)


def _is_long_range(asset) -> bool:
    return asset.distance_band == DistanceBand.long_range or "long_range" in asset.tags


def _label_summary(manifest: TrainingDatasetManifest) -> DatasetReadinessLabelSummary:
    expected_tasks = _EXPECTED_ANNOTATIONS_BY_TASK[manifest.task]
    expected_set = set(expected_tasks)
    assets_with_labels = 0
    missing_assets = 0
    for asset in manifest.assets:
        if expected_set.issubset(set(asset.annotations)):
            assets_with_labels += 1
        else:
            missing_assets += 1

    return DatasetReadinessLabelSummary(
        expected_annotation_tasks=[task.value for task in expected_tasks],
        assets_with_expected_annotations=assets_with_labels,
        assets_missing_expected_annotations=missing_assets,
        split_label_paths=sum(1 for split in manifest.splits if split.label_path),
    )


def _add_threshold_issue(
    issues: list[DatasetReadinessIssue],
    *,
    scope: str,
    label: str,
    actual: int,
    minimum: int,
) -> None:
    if actual < minimum:
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope=scope,
                message=f"{label} {actual} is below required minimum {minimum}",
            )
        )


def _count_missing_files(repo_root: Path, manifest: TrainingDatasetManifest, storage_root: Path) -> tuple[int, list[str]]:
    missing = 0
    examples: list[str] = []
    for asset in manifest.assets:
        path = storage_root / asset.relative_path
        if not path.exists():
            missing += 1
            if len(examples) < 5:
                examples.append(str(path))
    for split in manifest.splits:
        split_path = storage_root / split.relative_path
        if not split_path.exists():
            missing += 1
            if len(examples) < 5:
                examples.append(str(split_path))
        if split.label_path:
            label_path = storage_root / split.label_path
            if not label_path.exists():
                missing += 1
                if len(examples) < 5:
                    examples.append(str(label_path))
    return missing, examples


def audit_dataset_readiness(
    *,
    repo_root: Path,
    manifest: TrainingDatasetManifest,
    policy: DatasetReadinessPolicy | None = None,
) -> DatasetReadinessReport:
    active_policy = policy or build_dataset_readiness_policy()
    thresholds = active_policy.thresholds_by_task.get(manifest.task, DatasetReadinessThresholds())
    issues: list[DatasetReadinessIssue] = []
    split_samples = _split_samples(manifest)
    total_samples = _total_samples(manifest, split_samples)
    label_summary = _label_summary(manifest)
    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    capture_sessions = {asset.capture_session_id for asset in manifest.assets}
    for split in manifest.splits:
        capture_sessions.update(split.capture_session_ids)

    low_light_assets = sum(1 for asset in manifest.assets if _is_low_light(asset))
    long_range_assets = sum(1 for asset in manifest.assets if _is_long_range(asset))
    synthetic_train_samples = _synthetic_train_samples(manifest, split_samples)
    train_samples = split_samples.get(DatasetSplit.train.value, len(_assets_for_split(manifest, DatasetSplit.train)))
    synthetic_fraction = synthetic_train_samples / train_samples if train_samples else 0.0
    tag_counts = Counter(tag for asset in manifest.assets for tag in asset.tags)
    missing_files = 0

    if active_policy.require_approved_review and manifest.review_status != DatasetReviewStatus.approved:
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope="review",
                message="dataset review_status must be approved for this readiness gate",
            )
        )

    if active_policy.require_annotation_review:
        if manifest.annotation_review is None:
            issues.append(
                DatasetReadinessIssue(
                    severity="error",
                    scope="review",
                    message="dataset must include annotation_review before it can be used for production training",
                )
            )
        else:
            accepted = set(manifest.annotation_review.accepted_tasks)
            missing_tasks = [task.value for task in _EXPECTED_ANNOTATIONS_BY_TASK[manifest.task] if task not in accepted]
            if missing_tasks:
                issues.append(
                    DatasetReadinessIssue(
                        severity="error",
                        scope="review",
                        message=f"annotation_review is missing accepted task(s): {', '.join(missing_tasks)}",
                    )
                )

    if active_policy.require_license_review:
        if manifest.provenance.license_tier == DatasetLicenseTier.unknown:
            issues.append(
                DatasetReadinessIssue(
                    severity="error",
                    scope="license",
                    message="dataset license_tier is unknown; license review is required before production training",
                )
            )
        elif manifest.provenance.license_tier not in active_policy.allowed_license_tiers:
            issues.append(
                DatasetReadinessIssue(
                    severity="error",
                    scope="license",
                    message=f"dataset license_tier {manifest.provenance.license_tier.value} is not allowed by policy",
                )
            )

    if active_policy.verify_files:
        missing_files, examples = _count_missing_files(repo_root, manifest, storage_root)
        if missing_files:
            detail = "; examples: " + "; ".join(examples) if examples else ""
            issues.append(
                DatasetReadinessIssue(
                    severity="error",
                    scope="files",
                    message=f"{missing_files} required dataset file/path entries are missing{detail}",
                )
            )

    if manifest.format == DatasetFormat.eval_holdout:
        _add_threshold_issue(
            issues,
            scope="coverage",
            label="field_eval samples",
            actual=split_samples.get(DatasetSplit.field_eval.value, total_samples),
            minimum=thresholds.min_field_eval_samples,
        )
    else:
        _add_threshold_issue(
            issues,
            scope="coverage",
            label="train samples",
            actual=split_samples.get(DatasetSplit.train.value, 0),
            minimum=thresholds.min_train_samples,
        )
        _add_threshold_issue(
            issues,
            scope="coverage",
            label="validation samples",
            actual=split_samples.get(DatasetSplit.validation.value, 0),
            minimum=thresholds.min_validation_samples,
        )
        _add_threshold_issue(
            issues,
            scope="coverage",
            label="holdout samples",
            actual=split_samples.get(DatasetSplit.holdout.value, 0),
            minimum=thresholds.min_holdout_samples,
        )

    _add_threshold_issue(
        issues,
        scope="coverage",
        label="total samples",
        actual=total_samples,
        minimum=thresholds.min_total_samples,
    )
    _add_threshold_issue(
        issues,
        scope="coverage",
        label="capture sessions",
        actual=len(capture_sessions),
        minimum=thresholds.min_capture_sessions,
    )

    if active_policy.require_capture_session_metadata and not capture_sessions:
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope="metadata",
                message="capture-session metadata is required to prevent train/holdout leakage",
            )
        )

    if active_policy.require_condition_metadata and manifest.assets:
        _add_threshold_issue(
            issues,
            scope="coverage",
            label="low-light assets",
            actual=low_light_assets,
            minimum=thresholds.min_low_light_assets,
        )
        _add_threshold_issue(
            issues,
            scope="coverage",
            label="long-range assets",
            actual=long_range_assets,
            minimum=thresholds.min_long_range_assets,
        )
    elif active_policy.require_condition_metadata and (thresholds.min_low_light_assets or thresholds.min_long_range_assets):
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope="metadata",
                message="asset-level lighting and distance metadata is required to prove Oklahoma night/long-range coverage",
            )
        )

    if train_samples and synthetic_fraction > thresholds.max_synthetic_train_fraction:
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope="provenance",
                message=(
                    f"synthetic train fraction {synthetic_fraction:.2%} exceeds maximum "
                    f"{thresholds.max_synthetic_train_fraction:.2%}"
                ),
            )
        )

    if manifest.assets and label_summary.assets_missing_expected_annotations:
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope="labels",
                message=(
                    f"{label_summary.assets_missing_expected_annotations} asset(s) are missing required annotation "
                    f"task(s): {', '.join(label_summary.expected_annotation_tasks)}"
                ),
            )
        )
    elif not manifest.assets and not label_summary.split_label_paths:
        issues.append(
            DatasetReadinessIssue(
                severity="error",
                scope="labels",
                message="dataset has no asset-level annotations and no split label paths",
            )
        )

    if manifest.task != DatasetTask.plate_ocr:
        for tag, minimum in active_policy.required_asset_tag_samples.items():
            actual = tag_counts.get(tag, 0)
            if actual < minimum:
                issues.append(
                    DatasetReadinessIssue(
                        severity="error",
                        scope="oklahoma_vehicle_coverage",
                        message=f"asset tag '{tag}' count {actual} is below required minimum {minimum}",
                    )
                )

    return DatasetReadinessReport(
        dataset_name=manifest.dataset_name,
        dataset_version=manifest.dataset_version,
        task=manifest.task,
        generated_at_utc=_utcnow(),
        ready=not any(issue.severity == "error" for issue in issues),
        policy_name=active_policy.policy_name,
        storage_root=str(storage_root),
        total_samples=total_samples,
        total_assets=len(manifest.assets),
        split_samples=split_samples,
        capture_sessions=len(capture_sessions),
        low_light_assets=low_light_assets,
        long_range_assets=long_range_assets,
        synthetic_train_samples=synthetic_train_samples,
        missing_files=missing_files,
        asset_tag_counts=dict(sorted(tag_counts.items())),
        label_summary=label_summary,
        thresholds=thresholds,
        issues=issues,
    )
