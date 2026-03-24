"""Promoted-model benchmark and evaluation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from PIL import Image

from reposcan_contracts.benchmark import (
    BenchmarkFrameExpectation,
    BenchmarkSubsetMetrics,
    BenchmarkValidationSummary,
    PromotedModelBenchmarkManifest,
    PromotedModelBenchmarkReport,
)
from reposcan_contracts.dataset import DatasetReviewStatus, DistanceBand, LightingCondition, TrainingDatasetManifest
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType

from .deployment_validation import validate_deployment_runtime_bundle
from .promotion import validate_promoted_model_stack
from .service import InferenceService

_LOW_LIGHT_CONDITIONS = {
    LightingCondition.dusk,
    LightingCondition.night,
    LightingCondition.no_light,
    LightingCondition.ir_assisted,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value.strip().lower())
    collapsed = "_".join(part for part in normalized.split("_") if part)
    return collapsed or "benchmark"


def _resolve_storage_root(repo_root: Path, storage_root: str) -> Path:
    root = Path(storage_root)
    if root.is_absolute():
        return root
    return (repo_root / root).resolve()


def _derived_tags(asset) -> list[str]:
    tags = {tag for tag in asset.tags if tag}
    if asset.distance_band == DistanceBand.long_range:
        tags.add("long_range")
    if any(condition in _LOW_LIGHT_CONDITIONS for condition in asset.lighting_conditions):
        tags.add("low_light")
    if LightingCondition.glare in asset.lighting_conditions:
        tags.add("glare")
    if LightingCondition.no_light in asset.lighting_conditions:
        tags.add("no_light")
    if LightingCondition.ir_assisted in asset.lighting_conditions:
        tags.add("ir_assisted")
    return sorted(tags)


def build_benchmark_manifest_from_eval_holdout(
    *,
    repo_root: Path,
    dataset_manifest: TrainingDatasetManifest,
    dataset_manifest_path: Path | None = None,
    benchmark_name: str | None = None,
    camera_id: str | None = None,
    description: str | None = None,
) -> PromotedModelBenchmarkManifest:
    if dataset_manifest.format.value != "eval_holdout":
        raise ValueError("dataset-backed benchmarking requires a dataset manifest with format=eval_holdout")
    if dataset_manifest.review_status != DatasetReviewStatus.approved:
        raise ValueError("dataset-backed benchmarking requires an approved eval-holdout dataset manifest")
    if not dataset_manifest.assets:
        raise ValueError("eval-holdout dataset manifest must contain asset-level records")

    storage_root = _resolve_storage_root(repo_root, dataset_manifest.storage_root)
    frames: list[BenchmarkFrameExpectation] = []
    missing_expectations: list[str] = []

    for asset in dataset_manifest.assets:
        if not any(
            [
                asset.expected_plate_text,
                asset.vehicle_color,
                asset.vehicle_make,
                asset.vehicle_model,
                asset.vehicle_year,
            ]
        ):
            missing_expectations.append(asset.asset_id)
            continue

        frame_path = storage_root / asset.relative_path
        if not frame_path.exists():
            raise ValueError(f"dataset asset path does not exist: {frame_path}")
        frames.append(
            BenchmarkFrameExpectation(
                frame_path=str(frame_path),
                timestamp_utc=asset.timestamp_utc,
                expected_plate_text=asset.expected_plate_text,
                expected_vehicle_color=asset.vehicle_color,
                expected_vehicle_make=asset.vehicle_make,
                expected_vehicle_model=asset.vehicle_model,
                expected_vehicle_year=asset.vehicle_year,
                tags=_derived_tags(asset),
            )
        )

    if missing_expectations:
        raise ValueError(
            "eval-holdout assets require at least one expected benchmark field; missing expectations for asset_ids: "
            + ", ".join(missing_expectations[:10])
        )
    if not frames:
        raise ValueError("no benchmarkable assets were found in the eval-holdout dataset manifest")

    manifest_description = description
    if manifest_description is None:
        source_text = f" from {dataset_manifest_path}" if dataset_manifest_path is not None else ""
        manifest_description = (
            f"Benchmark manifest derived from eval-holdout dataset '{dataset_manifest.dataset_name}'{source_text}."
        )

    return PromotedModelBenchmarkManifest(
        benchmark_name=benchmark_name or f"{dataset_manifest.dataset_name}-benchmark",
        description=manifest_description,
        camera_id=camera_id or f"cam_eval_{_slug(dataset_manifest.dataset_name)}",
        frames=frames,
    )


def _levenshtein_distance(expected: str, actual: str) -> int:
    if expected == actual:
        return 0
    if not expected:
        return len(actual)
    if not actual:
        return len(expected)

    previous = list(range(len(actual) + 1))
    for i, expected_char in enumerate(expected, start=1):
        current = [i]
        for j, actual_char in enumerate(actual, start=1):
            cost = 0 if expected_char == actual_char else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def _character_accuracy(expected: str, actual: str) -> float:
    denominator = max(len(expected), len(actual), 1)
    distance = _levenshtein_distance(expected, actual)
    return max(0.0, 1.0 - (distance / denominator))


def _frame_envelope(camera_id: str, frame: BenchmarkFrameExpectation, *, index: int) -> FrameEnvelope:
    frame_path = Path(frame.frame_path)
    with Image.open(frame_path) as image:
        width, height = image.size

    timestamp = frame.timestamp_utc or f"2026-03-23T12:00:{index:02d}Z"
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"frm_benchmark_{index:04d}",
            "camera_id": camera_id,
            "timestamp_utc": timestamp,
            "frame_path": str(frame_path),
            "frame_number": index,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id=camera_id,
                source_type=SourceType.file,
                resolution_w=width,
                resolution_h=height,
            ).model_dump(mode="json"),
        }
    )


def _measure_subset(
    inference_service: InferenceService,
    camera_id: str,
    frames: list[BenchmarkFrameExpectation],
) -> BenchmarkSubsetMetrics:
    exact_match_total = 0
    exact_match_hits = 0
    character_total = 0.0
    character_count = 0
    color_total = 0
    color_hits = 0
    make_total = 0
    make_hits = 0
    latencies: list[float] = []
    vehicles_per_frame: list[int] = []
    plates_per_frame: list[int] = []

    for index, frame in enumerate(frames, start=1):
        candidate = inference_service.run(_frame_envelope(camera_id, frame, index=index))
        predicted_plate = candidate.ocr_candidates[0].text if candidate.ocr_candidates else None
        predicted_attributes = candidate.attribute_predictions[0] if candidate.attribute_predictions else None

        latencies.append(candidate.processing_latency_ms)
        vehicles_per_frame.append(len(candidate.vehicle_detections))
        plates_per_frame.append(len(candidate.plate_detections))

        if frame.expected_plate_text:
            exact_match_total += 1
            if predicted_plate == frame.expected_plate_text:
                exact_match_hits += 1
            character_total += _character_accuracy(frame.expected_plate_text, predicted_plate or "")
            character_count += 1

        if frame.expected_vehicle_color:
            color_total += 1
            if predicted_attributes and predicted_attributes.color == frame.expected_vehicle_color:
                color_hits += 1

        if frame.expected_vehicle_make:
            make_total += 1
            if predicted_attributes and predicted_attributes.make == frame.expected_vehicle_make:
                make_hits += 1

    sorted_latencies = sorted(latencies)
    p95_index = max(0, int(len(sorted_latencies) * 0.95) - 1) if sorted_latencies else 0

    return BenchmarkSubsetMetrics(
        frames=len(frames),
        exact_match_rate=(exact_match_hits / exact_match_total) if exact_match_total else None,
        character_accuracy=(character_total / character_count) if character_count else None,
        color_accuracy=(color_hits / color_total) if color_total else None,
        make_accuracy=(make_hits / make_total) if make_total else None,
        average_latency_ms=mean(sorted_latencies) if sorted_latencies else None,
        p95_latency_ms=sorted_latencies[p95_index] if sorted_latencies else None,
        max_latency_ms=max(sorted_latencies) if sorted_latencies else None,
        average_vehicles_per_frame=mean(vehicles_per_frame) if vehicles_per_frame else None,
        average_plates_per_frame=mean(plates_per_frame) if plates_per_frame else None,
    )


def _validation_summary(inference_service: InferenceService, deployment) -> BenchmarkValidationSummary:
    if deployment is None:
        promotion_report = validate_promoted_model_stack(inference_service.model_stack)
        issues = [issue.message for stage in promotion_report.stages for issue in stage.issues]
        return BenchmarkValidationSummary(
            runtime_ready=promotion_report.runtime_ready,
            promotion_ready=promotion_report.ready,
            deployment_ready=None,
            deployment_name=None,
            issues=issues,
        )

    deployment_report = validate_deployment_runtime_bundle(inference_service.model_stack, deployment)
    return BenchmarkValidationSummary(
        runtime_ready=deployment_report.runtime_ready,
        promotion_ready=deployment_report.promotion_ready,
        deployment_ready=deployment_report.ready,
        deployment_name=deployment_report.deployment_name,
        issues=[issue.message for issue in deployment_report.issues],
    )


def benchmark_promoted_model(
    inference_service: InferenceService,
    manifest: PromotedModelBenchmarkManifest,
    *,
    deployment=None,
    benchmark_manifest_path: Path | None = None,
    source_dataset_manifest: TrainingDatasetManifest | None = None,
    source_dataset_manifest_path: Path | None = None,
) -> PromotedModelBenchmarkReport:
    overall = _measure_subset(inference_service, manifest.camera_id, manifest.frames)

    subsets: dict[str, BenchmarkSubsetMetrics] = {}
    tag_names = sorted({tag for frame in manifest.frames for tag in frame.tags})
    for tag in tag_names:
        subset_frames = [frame for frame in manifest.frames if tag in frame.tags]
        subsets[tag] = _measure_subset(inference_service, manifest.camera_id, subset_frames)

    return PromotedModelBenchmarkReport(
        benchmark_name=manifest.benchmark_name,
        model_stack_name=inference_service.model_stack.stack_name,
        generated_at_utc=_utcnow(),
        benchmark_manifest_path=str(benchmark_manifest_path) if benchmark_manifest_path is not None else None,
        source_dataset_name=source_dataset_manifest.dataset_name if source_dataset_manifest is not None else None,
        source_dataset_version=source_dataset_manifest.dataset_version if source_dataset_manifest is not None else None,
        source_dataset_manifest_path=str(source_dataset_manifest_path) if source_dataset_manifest_path is not None else None,
        overall=overall,
        subsets=subsets,
        validation=_validation_summary(inference_service, deployment),
    )
