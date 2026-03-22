"""Artifact-backed runtime adapters for the local no-hardware demo path.

These adapters are intentionally simple and deterministic. They read tracked
artifact manifests from the repo and can also consume per-frame sidecar files
to vary detections across a test sequence without camera hardware or trained
model exports.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from math import sqrt
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageStat, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError

from reposcan_contracts.config.model import (
    ClassifierModelConfig,
    DetectorModelConfig,
    InferenceBackend,
    ModelStackConfig,
    OcrModelConfig,
)
from reposcan_contracts.config.pipeline import PlateDetectionStrategy
from reposcan_contracts.detection import BoundingBox, PlateCandidate
from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import AttributePredictions, PlateDetection, VehicleDetection

from .adapters import ModelAdapterBundle

InferenceFrame = FrameEnvelope | PreparedFrame

_MAX_COLOR_DISTANCE = sqrt(3 * (255**2))
_DEFAULT_COLOR_PALETTE: dict[str, tuple[int, int, int]] = {
    "white": (232, 232, 232),
    "black": (30, 30, 30),
    "silver": (192, 192, 192),
    "gray": (128, 128, 128),
    "blue": (52, 92, 182),
    "red": (190, 52, 48),
    "green": (48, 138, 74),
    "yellow": (222, 190, 62),
    "orange": (220, 128, 54),
    "brown": (122, 84, 52),
    "other": (120, 120, 120),
}


class RelativeBoundingBox(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., gt=0.0, le=1.0)
    h: float = Field(..., gt=0.0, le=1.0)


class BuiltinVehicleDetectorArtifact(BaseModel):
    artifact_type: str = Field(pattern="^builtin_vehicle_detector$")
    default_class_label: str = "car"
    default_confidence: float = Field(0.9, ge=0.0, le=1.0)
    bbox_relative: RelativeBoundingBox


class BuiltinPlateDetectorArtifact(BaseModel):
    artifact_type: str = Field(pattern="^builtin_plate_detector$")
    default_confidence: float = Field(0.88, ge=0.0, le=1.0)
    bbox_relative_to_vehicle: RelativeBoundingBox
    bbox_relative_to_frame: RelativeBoundingBox


class BuiltinOcrArtifact(BaseModel):
    artifact_type: str = Field(pattern="^builtin_ocr$")
    default_plate_text: str = Field(..., min_length=1)
    default_confidence: float = Field(0.93, ge=0.0, le=1.0)
    filename_pattern: str = Field(..., min_length=1)


class BuiltinClassifierArtifact(BaseModel):
    artifact_type: str = Field(pattern="^builtin_classifier$")
    default_make: str = "other"
    default_make_confidence: float = Field(0.7, ge=0.0, le=1.0)
    default_model: str = "other"
    default_model_confidence: float = Field(0.65, ge=0.0, le=1.0)
    default_year: str | None = None
    default_year_confidence: float | None = Field(None, ge=0.0, le=1.0)


class FrameInferenceSidecar(BaseModel):
    vehicle_detections: list[VehicleDetection] = Field(default_factory=list)
    plate_detections: list[PlateDetection] = Field(default_factory=list)
    ocr_candidates: list[PlateCandidate] = Field(default_factory=list)
    attribute_predictions: list[AttributePredictions] = Field(default_factory=list)


def _frame_image_path(frame: InferenceFrame) -> Path:
    if isinstance(frame, PreparedFrame):
        return Path(frame.prepared_frame_path)
    return Path(frame.frame_path)


def _frame_raw_path(frame: InferenceFrame) -> Path:
    if isinstance(frame, PreparedFrame):
        return Path(frame.raw_frame_path)
    return Path(frame.frame_path)


def _candidate_paths(frame: InferenceFrame) -> list[Path]:
    seen: set[str] = set()
    candidates: list[Path] = []
    for candidate in (_frame_image_path(frame), _frame_raw_path(frame)):
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _sidecar_paths(frame: InferenceFrame) -> list[Path]:
    return [path.with_suffix(".inference.json") for path in _candidate_paths(frame)]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in '{path}'")
    return data


@lru_cache(maxsize=64)
def _load_sidecar(path: str) -> FrameInferenceSidecar:
    sidecar_path = Path(path)
    if not sidecar_path.exists():
        return FrameInferenceSidecar()
    try:
        return FrameInferenceSidecar.model_validate(_load_json(sidecar_path))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError):
        # Keep the runtime resilient for demo flows; invalid sidecars degrade
        # back to artifact defaults instead of crashing the entire ingest path.
        return FrameInferenceSidecar()


def _frame_sidecar(frame: InferenceFrame) -> FrameInferenceSidecar:
    for sidecar_path in _sidecar_paths(frame):
        sidecar = _load_sidecar(str(sidecar_path))
        if sidecar.vehicle_detections or sidecar.plate_detections or sidecar.ocr_candidates or sidecar.attribute_predictions:
            return sidecar
    return FrameInferenceSidecar()


def _open_image(frame: InferenceFrame) -> Image.Image | None:
    for candidate in _candidate_paths(frame):
        if not candidate.exists():
            continue
        try:
            with Image.open(candidate) as image:
                return image.convert("RGB")
        except (OSError, UnidentifiedImageError):
            continue
    return None


def _image_dimensions(frame: InferenceFrame) -> tuple[int, int] | None:
    image = _open_image(frame)
    if image is None:
        width = frame.camera_profile.resolution_w
        height = frame.camera_profile.resolution_h
        if width is not None and height is not None:
            return (width, height)
        return None
    return image.size


def _mean_rgb(frame: InferenceFrame) -> tuple[float, float, float] | None:
    image = _open_image(frame)
    if image is None:
        return None
    stat = ImageStat.Stat(image)
    mean = stat.mean
    return (mean[0], mean[1], mean[2])


def _absolute_bbox(relative: RelativeBoundingBox, *, width: int, height: int) -> BoundingBox:
    x = min(int(width * relative.x), max(width - 1, 0))
    y = min(int(height * relative.y), max(height - 1, 0))
    w = max(1, min(int(width * relative.w), max(width - x, 1)))
    h = max(1, min(int(height * relative.h), max(height - y, 1)))
    return BoundingBox(x=x, y=y, w=w, h=h)


def _bbox_within_vehicle(relative: RelativeBoundingBox, vehicle_bbox: BoundingBox) -> BoundingBox:
    x = vehicle_bbox.x + int(vehicle_bbox.w * relative.x)
    y = vehicle_bbox.y + int(vehicle_bbox.h * relative.y)
    max_width = max(1, (vehicle_bbox.x + vehicle_bbox.w) - x)
    max_height = max(1, (vehicle_bbox.y + vehicle_bbox.h) - y)
    w = max(1, min(int(vehicle_bbox.w * relative.w), max_width))
    h = max(1, min(int(vehicle_bbox.h * relative.h), max_height))
    return BoundingBox(x=x, y=y, w=w, h=h)


def _plate_text_from_filename(frame: InferenceFrame, pattern: str) -> str | None:
    regex = re.compile(pattern)
    for candidate in _candidate_paths(frame):
        stem = candidate.stem.upper()
        matches = regex.findall(stem)
        for match in matches:
            text = match if isinstance(match, str) else "".join(match)
            if any(character.isalpha() for character in text) and any(character.isdigit() for character in text):
                return text
    return None


def _nearest_color_label(
    mean_rgb: tuple[float, float, float] | None,
    color_labels: Sequence[str],
) -> tuple[str | None, float | None]:
    if mean_rgb is None:
        return None, None

    palette = {
        label: _DEFAULT_COLOR_PALETTE[label]
        for label in color_labels
        if label in _DEFAULT_COLOR_PALETTE
    }
    if not palette:
        return None, None

    best_label: str | None = None
    best_distance: float | None = None
    for label, rgb in palette.items():
        distance = sqrt(sum((component - palette_component) ** 2 for component, palette_component in zip(mean_rgb, rgb)))
        if best_distance is None or distance < best_distance:
            best_label = label
            best_distance = distance

    if best_label is None or best_distance is None:
        return None, None

    confidence = max(0.0, 1.0 - (best_distance / _MAX_COLOR_DISTANCE))
    return best_label, confidence


@lru_cache(maxsize=16)
def _load_vehicle_artifact(path: str) -> BuiltinVehicleDetectorArtifact:
    return BuiltinVehicleDetectorArtifact.model_validate(_load_json(Path(path)))


@lru_cache(maxsize=16)
def _load_plate_artifact(path: str) -> BuiltinPlateDetectorArtifact:
    return BuiltinPlateDetectorArtifact.model_validate(_load_json(Path(path)))


@lru_cache(maxsize=16)
def _load_ocr_artifact(path: str) -> BuiltinOcrArtifact:
    return BuiltinOcrArtifact.model_validate(_load_json(Path(path)))


@lru_cache(maxsize=16)
def _load_classifier_artifact(path: str) -> BuiltinClassifierArtifact:
    return BuiltinClassifierArtifact.model_validate(_load_json(Path(path)))


class BuiltinVehicleDetectorAdapter:
    def __init__(self, model_config: DetectorModelConfig) -> None:
        self.model_config = model_config
        self.artifact = _load_vehicle_artifact(model_config.artifact_path)

    def detect(self, frame: InferenceFrame) -> list[VehicleDetection]:
        sidecar = _frame_sidecar(frame)
        if sidecar.vehicle_detections:
            return list(sidecar.vehicle_detections)

        dimensions = _image_dimensions(frame)
        if dimensions is None:
            return []
        width, height = dimensions
        return [
            VehicleDetection(
                bbox=_absolute_bbox(self.artifact.bbox_relative, width=width, height=height),
                confidence=max(self.model_config.confidence_threshold, self.artifact.default_confidence),
                class_label=self.artifact.default_class_label,
            )
        ]


class BuiltinPlateDetectorAdapter:
    def __init__(self, model_config: DetectorModelConfig) -> None:
        self.model_config = model_config
        self.artifact = _load_plate_artifact(model_config.artifact_path)

    def detect(
        self,
        frame: InferenceFrame,
        *,
        vehicle_detections: Sequence[VehicleDetection],
        strategy: PlateDetectionStrategy,
    ) -> list[PlateDetection]:
        sidecar = _frame_sidecar(frame)
        if sidecar.plate_detections:
            return list(sidecar.plate_detections)

        if strategy == PlateDetectionStrategy.vehicle_crop and vehicle_detections:
            return [
                PlateDetection(
                    bbox=_bbox_within_vehicle(self.artifact.bbox_relative_to_vehicle, vehicle_detections[0].bbox),
                    confidence=max(self.model_config.confidence_threshold, self.artifact.default_confidence),
                    vehicle_index=0,
                )
            ]

        dimensions = _image_dimensions(frame)
        if dimensions is None:
            return []
        width, height = dimensions
        return [
            PlateDetection(
                bbox=_absolute_bbox(self.artifact.bbox_relative_to_frame, width=width, height=height),
                confidence=max(self.model_config.confidence_threshold, self.artifact.default_confidence),
                vehicle_index=0 if len(vehicle_detections) == 1 else None,
            )
        ]


class BuiltinOcrAdapter:
    def __init__(self, model_config: OcrModelConfig, *, default_plate_text: str | None = None) -> None:
        self.model_config = model_config
        self.artifact = _load_ocr_artifact(model_config.artifact_path)
        self.default_plate_text = default_plate_text

    def recognize(self, frame: InferenceFrame, plate_detections: Sequence[PlateDetection]) -> list[PlateCandidate]:
        if not plate_detections:
            return []

        sidecar = _frame_sidecar(frame)
        if sidecar.ocr_candidates:
            return list(sidecar.ocr_candidates)

        plate_text = (
            _plate_text_from_filename(frame, self.artifact.filename_pattern)
            or self.default_plate_text
            or self.artifact.default_plate_text
        )
        return [
            PlateCandidate(
                text=plate_text,
                confidence=max(self.model_config.confidence_threshold, self.artifact.default_confidence),
            )
        ]


class BuiltinClassifierAdapter:
    def __init__(self, model_config: ClassifierModelConfig) -> None:
        self.model_config = model_config
        self.artifact = _load_classifier_artifact(model_config.artifact_path)

    def predict(
        self,
        frame: InferenceFrame,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        if not vehicle_detections or not self.model_config.enabled:
            return []

        sidecar = _frame_sidecar(frame)
        if sidecar.attribute_predictions:
            return list(sidecar.attribute_predictions)

        color_label, color_confidence = _nearest_color_label(_mean_rgb(frame), self.model_config.color_labels)
        prediction = AttributePredictions.model_validate(
            {
                "color": color_label,
                "color_confidence": color_confidence,
                "make": self.artifact.default_make,
                "make_confidence": self.artifact.default_make_confidence,
                "model": self.artifact.default_model,
                "model_confidence": self.artifact.default_model_confidence,
                "year": self.artifact.default_year,
                "year_confidence": self.artifact.default_year_confidence,
            }
        )
        return [prediction for _ in vehicle_detections]


def build_runtime_adapter_bundle(
    model_stack: ModelStackConfig,
    *,
    default_plate_text: str | None = None,
) -> ModelAdapterBundle | None:
    backend_values = {
        model_stack.vehicle_detector.backend,
        model_stack.plate_detector.backend,
        model_stack.ocr.backend,
    }
    if model_stack.classifier is not None:
        backend_values.add(model_stack.classifier.backend)

    if backend_values != {InferenceBackend.builtin}:
        return None

    classifier = None
    if model_stack.classifier is not None:
        classifier = BuiltinClassifierAdapter(model_stack.classifier)

    return ModelAdapterBundle(
        vehicle_detector=BuiltinVehicleDetectorAdapter(model_stack.vehicle_detector),
        plate_detector=BuiltinPlateDetectorAdapter(model_stack.plate_detector),
        ocr=BuiltinOcrAdapter(model_stack.ocr, default_plate_text=default_plate_text),
        classifier=classifier,
    )
