"""Promoted-model benchmark scaffolding for local evaluation runs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

from reposcan_contracts.benchmark import BenchmarkFrameExpectation, PromotedModelBenchmarkManifest
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType

from .service import InferenceService


class BenchmarkSubsetMetrics(BaseModel):
    frames: int
    exact_match_rate: float | None = None
    character_accuracy: float | None = None
    color_accuracy: float | None = None
    make_accuracy: float | None = None


class PromotedModelBenchmarkReport(BaseModel):
    benchmark_name: str
    model_stack_name: str
    overall: BenchmarkSubsetMetrics
    subsets: dict[str, BenchmarkSubsetMetrics] = Field(default_factory=dict)


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

    for index, frame in enumerate(frames, start=1):
        candidate = inference_service.run(_frame_envelope(camera_id, frame, index=index))
        predicted_plate = candidate.ocr_candidates[0].text if candidate.ocr_candidates else None
        predicted_attributes = candidate.attribute_predictions[0] if candidate.attribute_predictions else None

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

    return BenchmarkSubsetMetrics(
        frames=len(frames),
        exact_match_rate=(exact_match_hits / exact_match_total) if exact_match_total else None,
        character_accuracy=(character_total / character_count) if character_count else None,
        color_accuracy=(color_hits / color_total) if color_total else None,
        make_accuracy=(make_hits / make_total) if make_total else None,
    )


def benchmark_promoted_model(
    inference_service: InferenceService,
    manifest: PromotedModelBenchmarkManifest,
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
        overall=overall,
        subsets=subsets,
    )
