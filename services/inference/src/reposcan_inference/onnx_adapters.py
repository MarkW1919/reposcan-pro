"""ONNX runtime adapters for the inference service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

from reposcan_contracts.classifier_export import ClassifierExportMetadata, parse_vehicle_make_model_year
from reposcan_contracts.config.model import ClassifierModelConfig, DetectorModelConfig, InferenceBackend, ModelStackConfig, OcrModelConfig
from reposcan_contracts.config.pipeline import PlateDetectionStrategy
from reposcan_contracts.dataset import DatasetTask
from reposcan_contracts.detection import BoundingBox, PlateCandidate
from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import AttributePredictions, PlateDetection, VehicleDetection

from .adapters import ModelAdapterBundle
from .runtime_adapters import _frame_sidecar, _open_image

InferenceFrame = FrameEnvelope | PreparedFrame

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover - handled through validation and factory fallbacks
    ort = None


def _require_onnxruntime():
    if ort is None:
        raise RuntimeError("onnxruntime is not installed in the active Python environment.")
    return ort


def _artifact_exists(path: str | Path) -> bool:
    return Path(path).exists()


def _blank_image(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (max(width, 1), max(height, 1)), color=(0, 0, 0))


def _full_image_or_blank(frame: InferenceFrame, *, width: int, height: int) -> Image.Image:
    image = _open_image(frame)
    if image is None:
        return _blank_image(width, height)
    return image


def _crop_or_blank(image: Image.Image | None, bbox: BoundingBox, *, fallback_width: int, fallback_height: int) -> Image.Image:
    if image is None:
        return _blank_image(fallback_width, fallback_height)

    left = max(0, bbox.x)
    top = max(0, bbox.y)
    right = min(image.width, bbox.x + bbox.w)
    bottom = min(image.height, bbox.y + bbox.h)
    if right <= left or bottom <= top:
        return _blank_image(fallback_width, fallback_height)
    return image.crop((left, top, right, bottom))


def _prepare_input(
    image: Image.Image,
    *,
    input_width: int,
    input_height: int,
    normalization_mean: Sequence[float],
    normalization_std: Sequence[float],
) -> np.ndarray:
    resized = image.resize((input_width, input_height))
    array = np.asarray(resized, dtype=np.float32) / 255.0
    array = np.transpose(array, (2, 0, 1))
    mean = np.asarray(list(normalization_mean), dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(list(normalization_std), dtype=np.float32).reshape(3, 1, 1)
    std = np.where(std == 0.0, 1.0, std)
    normalized = (array - mean) / std
    return normalized[np.newaxis, ...].astype(np.float32)


def _session_output_map(session, output_values: list[object]) -> dict[str, object]:
    return {
        output.name: value
        for output, value in zip(session.get_outputs(), output_values, strict=False)
    }


def _flatten(values: object) -> np.ndarray:
    return np.asarray(values).reshape(-1)


def _first_float(values: object, *, default: float = 0.0) -> float:
    flattened = _flatten(values)
    if flattened.size == 0:
        return default
    return float(flattened[0])


def _first_int(values: object, *, default: int = 0) -> int:
    flattened = _flatten(values)
    if flattened.size == 0:
        return default
    return int(flattened[0])


def _first_text(values: object, *, default: str | None = None) -> str | None:
    flattened = _flatten(values)
    if flattened.size == 0:
        return default
    value = flattened[0]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _softmax(logits: np.ndarray) -> np.ndarray:
    if logits.size == 0:
        return logits
    shifted = logits - np.max(logits)
    exp_values = np.exp(shifted)
    total = float(exp_values.sum())
    if total <= 0.0:
        return np.zeros_like(logits, dtype=np.float32)
    return (exp_values / total).astype(np.float32)


@lru_cache(maxsize=16)
def _load_classifier_metadata(path: str) -> ClassifierExportMetadata:
    return ClassifierExportMetadata.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _relative_bbox_to_absolute(relative_xywh: np.ndarray, *, width: int, height: int) -> BoundingBox:
    x = min(int(float(relative_xywh[0]) * width), max(width - 1, 0))
    y = min(int(float(relative_xywh[1]) * height), max(height - 1, 0))
    w = max(1, min(int(float(relative_xywh[2]) * width), max(width - x, 1)))
    h = max(1, min(int(float(relative_xywh[3]) * height), max(height - y, 1)))
    return BoundingBox(x=x, y=y, w=w, h=h)


def _validate_classifier_metadata(
    model_config: ClassifierModelConfig,
    *,
    metadata_path: Path | None,
) -> list[str]:
    if metadata_path is None:
        return ["Classifier exports with a 'logits' output require label_metadata_path in the model config."]
    if not metadata_path.exists():
        return [f"Classifier label metadata '{metadata_path}' does not exist."]
    try:
        metadata = _load_classifier_metadata(str(metadata_path))
    except Exception as exc:  # pragma: no cover - validation exercised indirectly
        return [str(exc)]
    if not metadata.class_records:
        return [f"Classifier label metadata '{metadata_path}' does not define any class_records."]
    return []


def _supports_structured_classifier_outputs(output_names: set[str]) -> bool:
    return {
        "color_indices",
        "color_confidences",
        "make_indices",
        "make_confidences",
        "model_texts",
        "model_confidences",
        "year_texts",
        "year_confidences",
    }.issubset(output_names)


def _attribute_prediction_from_logits(
    logits: object,
    *,
    metadata: ClassifierExportMetadata | None,
    model_config: ClassifierModelConfig,
) -> AttributePredictions:
    flattened_logits = np.asarray(logits, dtype=np.float32).reshape(-1)
    probabilities = _softmax(flattened_logits)
    if probabilities.size == 0:
        return AttributePredictions()

    best_index = int(np.argmax(probabilities))
    confidence = float(probabilities[best_index])
    record = metadata.record_for_index(best_index) if metadata is not None else None
    task = metadata.task if metadata is not None else None

    if task == DatasetTask.vehicle_color_classification.value:
        color_label = (record.color if record is not None else None) or (
            record.label.lower() if record is not None else None
        )
        if color_label is None and 0 <= best_index < len(model_config.color_labels):
            color_label = model_config.color_labels[best_index]
        return AttributePredictions.model_validate(
            {
                "color": color_label,
                "color_confidence": confidence,
            }
        )

    if task == DatasetTask.vehicle_make_model_classification.value:
        make_label = record.make if record is not None else None
        model_label = record.model_label if record is not None else None
        year_label = record.year if record is not None else None
        if record is not None and (make_label is None or model_label is None):
            parsed_make, parsed_model, parsed_year = parse_vehicle_make_model_year(record.label)
            make_label = make_label or parsed_make
            model_label = model_label or parsed_model
            year_label = year_label or parsed_year
        return AttributePredictions.model_validate(
            {
                "make": make_label,
                "make_confidence": confidence,
                "model": model_label,
                "model_confidence": confidence,
                "year": year_label,
                "year_confidence": confidence if year_label else None,
            }
        )

    if task == DatasetTask.vehicle_year_classification.value:
        year_label = (record.year if record is not None else None) or (record.label if record is not None else None)
        return AttributePredictions.model_validate(
            {
                "year": year_label,
                "year_confidence": confidence,
            }
        )

    if 0 <= best_index < len(model_config.color_labels):
        return AttributePredictions.model_validate(
            {
                "color": model_config.color_labels[best_index],
                "color_confidence": confidence,
            }
        )

    if 0 <= best_index < len(model_config.make_labels):
        return AttributePredictions.model_validate(
            {
                "make": model_config.make_labels[best_index],
                "make_confidence": confidence,
            }
        )

    fallback_label = record.label if record is not None else None
    return AttributePredictions.model_validate(
        {
            "model": fallback_label,
            "model_confidence": confidence if fallback_label else None,
        }
    )


@lru_cache(maxsize=16)
def _load_session(path: str):
    runtime = _require_onnxruntime()
    return runtime.InferenceSession(str(Path(path)), providers=["CPUExecutionProvider"])


def validate_onnx_artifact(
    stage: str,
    model_config: DetectorModelConfig | OcrModelConfig | ClassifierModelConfig,
    *,
    artifact_path: Path | None = None,
    metadata_path: Path | None = None,
) -> list[str]:
    issues: list[str] = []
    if model_config.backend != InferenceBackend.onnx:
        return issues

    if ort is None:
        return ["onnxruntime is not installed in the active Python environment."]

    artifact_path = artifact_path or Path(model_config.artifact_path)
    if artifact_path.suffix.lower() != ".onnx":
        issues.append(f"Expected an .onnx artifact for {stage}, found '{artifact_path.name}'.")
        return issues

    try:
        session = _load_session(str(artifact_path))
    except Exception as exc:  # pragma: no cover - exercised through validation tests indirectly
        return [str(exc)]

    try:
        input_name = session.get_inputs()[0].name
        zero_input = np.zeros((1, 3, model_config.input_height, model_config.input_width), dtype=np.float32)
        output_map = _session_output_map(session, session.run(None, {input_name: zero_input}))
    except Exception as exc:
        return [str(exc)]

    output_names = set(output_map.keys())
    required_outputs = {
        "vehicle_detector": {"boxes_xywh", "scores", "label_indices"},
        "plate_detector": {"boxes_xywh", "scores", "label_indices"},
        "ocr": {"texts", "confidences"},
    }
    if stage == "classifier":
        if _supports_structured_classifier_outputs(output_names):
            return issues
        if "logits" in output_names:
            assert isinstance(model_config, ClassifierModelConfig)
            issues.extend(_validate_classifier_metadata(model_config, metadata_path=metadata_path))
            return issues
        missing = sorted(
            {
                "color_indices",
                "color_confidences",
                "make_indices",
                "make_confidences",
                "model_texts",
                "model_confidences",
                "year_texts",
                "year_confidences",
            }
            - output_names
        )
        issues.append(
            "Missing required outputs for classifier: "
            + ", ".join(missing)
            + " (or provide a metadata-backed 'logits' export)."
        )
        return issues

    missing = sorted(required_outputs[stage] - output_names)
    if missing:
        issues.append(f"Missing required outputs for {stage}: {', '.join(missing)}")
    return issues


class OnnxVehicleDetectorAdapter:
    def __init__(self, model_config: DetectorModelConfig, *, artifact_path: str | Path | None = None) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path)
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, frame: InferenceFrame) -> list[VehicleDetection]:
        sidecar = _frame_sidecar(frame)
        if sidecar.vehicle_detections:
            return list(sidecar.vehicle_detections)

        image = _full_image_or_blank(
            frame,
            width=frame.camera_profile.resolution_w or self.model_config.input_width,
            height=frame.camera_profile.resolution_h or self.model_config.input_height,
        )
        tensor = _prepare_input(
            image,
            input_width=self.model_config.input_width,
            input_height=self.model_config.input_height,
            normalization_mean=self.model_config.normalization_mean,
            normalization_std=self.model_config.normalization_std,
        )
        outputs = _session_output_map(self.session, self.session.run(None, {self.input_name: tensor}))
        boxes = np.asarray(outputs["boxes_xywh"], dtype=np.float32).reshape(-1, 4)
        scores = _flatten(outputs["scores"])
        label_indices = _flatten(outputs["label_indices"])

        detections: list[VehicleDetection] = []
        for index, relative_box in enumerate(boxes):
            score = float(scores[index]) if index < scores.size else 0.0
            if score < self.model_config.confidence_threshold:
                continue
            label_index = int(label_indices[index]) if index < label_indices.size else 0
            class_label = (
                self.model_config.class_labels[label_index]
                if 0 <= label_index < len(self.model_config.class_labels)
                else "vehicle"
            )
            detections.append(
                VehicleDetection(
                    bbox=_relative_bbox_to_absolute(relative_box, width=image.width, height=image.height),
                    confidence=score,
                    class_label=class_label,
                )
            )
        return detections


class OnnxPlateDetectorAdapter:
    def __init__(self, model_config: DetectorModelConfig, *, artifact_path: str | Path | None = None) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path)
        self.input_name = self.session.get_inputs()[0].name

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

        frame_image = _open_image(frame)
        detections: list[PlateDetection] = []

        if strategy == PlateDetectionStrategy.vehicle_crop and not vehicle_detections:
            return []

        if strategy == PlateDetectionStrategy.vehicle_crop and vehicle_detections:
            for vehicle_index, vehicle_detection in enumerate(vehicle_detections):
                crop = _crop_or_blank(
                    frame_image,
                    vehicle_detection.bbox,
                    fallback_width=vehicle_detection.bbox.w,
                    fallback_height=vehicle_detection.bbox.h,
                )
                tensor = _prepare_input(
                    crop,
                    input_width=self.model_config.input_width,
                    input_height=self.model_config.input_height,
                    normalization_mean=self.model_config.normalization_mean,
                    normalization_std=self.model_config.normalization_std,
                )
                outputs = _session_output_map(self.session, self.session.run(None, {self.input_name: tensor}))
                boxes = np.asarray(outputs["boxes_xywh"], dtype=np.float32).reshape(-1, 4)
                scores = _flatten(outputs["scores"])
                for index, relative_box in enumerate(boxes):
                    score = float(scores[index]) if index < scores.size else 0.0
                    if score < self.model_config.confidence_threshold:
                        continue
                    crop_bbox = _relative_bbox_to_absolute(relative_box, width=crop.width, height=crop.height)
                    detections.append(
                        PlateDetection(
                            bbox=BoundingBox(
                                x=vehicle_detection.bbox.x + crop_bbox.x,
                                y=vehicle_detection.bbox.y + crop_bbox.y,
                                w=crop_bbox.w,
                                h=crop_bbox.h,
                            ),
                            confidence=score,
                            vehicle_index=vehicle_index,
                        )
                    )
            return detections

        full_image = _full_image_or_blank(
            frame,
            width=frame.camera_profile.resolution_w or self.model_config.input_width,
            height=frame.camera_profile.resolution_h or self.model_config.input_height,
        )
        tensor = _prepare_input(
            full_image,
            input_width=self.model_config.input_width,
            input_height=self.model_config.input_height,
            normalization_mean=self.model_config.normalization_mean,
            normalization_std=self.model_config.normalization_std,
        )
        outputs = _session_output_map(self.session, self.session.run(None, {self.input_name: tensor}))
        boxes = np.asarray(outputs["boxes_xywh"], dtype=np.float32).reshape(-1, 4)
        scores = _flatten(outputs["scores"])
        for index, relative_box in enumerate(boxes):
            score = float(scores[index]) if index < scores.size else 0.0
            if score < self.model_config.confidence_threshold:
                continue
            detections.append(
                PlateDetection(
                    bbox=_relative_bbox_to_absolute(relative_box, width=full_image.width, height=full_image.height),
                    confidence=score,
                    vehicle_index=0 if len(vehicle_detections) == 1 else None,
                )
            )
        return detections


class OnnxOcrAdapter:
    def __init__(
        self,
        model_config: OcrModelConfig,
        *,
        default_plate_text: str | None = None,
        artifact_path: str | Path | None = None,
    ) -> None:
        self.model_config = model_config
        self.default_plate_text = default_plate_text
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path)
        self.input_name = self.session.get_inputs()[0].name

    def recognize(self, frame: InferenceFrame, plate_detections: Sequence[PlateDetection]) -> list[PlateCandidate]:
        if not plate_detections:
            return []

        sidecar = _frame_sidecar(frame)
        if sidecar.ocr_candidates:
            return list(sidecar.ocr_candidates)

        frame_image = _open_image(frame)
        candidates: list[PlateCandidate] = []
        for plate_detection in plate_detections:
            crop = _crop_or_blank(
                frame_image,
                plate_detection.bbox,
                fallback_width=plate_detection.bbox.w,
                fallback_height=plate_detection.bbox.h,
            )
            tensor = _prepare_input(
                crop,
                input_width=self.model_config.input_width,
                input_height=self.model_config.input_height,
                normalization_mean=[0.0, 0.0, 0.0],
                normalization_std=[1.0, 1.0, 1.0],
            )
            outputs = _session_output_map(self.session, self.session.run(None, {self.input_name: tensor}))
            text = self.default_plate_text or _first_text(outputs["texts"]) or "UNKNOWN"
            confidence = max(self.model_config.confidence_threshold, _first_float(outputs["confidences"]))
            candidates.append(PlateCandidate(text=text, confidence=confidence))
        return candidates


class OnnxClassifierAdapter:
    def __init__(
        self,
        model_config: ClassifierModelConfig,
        *,
        artifact_path: str | Path | None = None,
        label_metadata_path: str | Path | None = None,
    ) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path)
        self.input_name = self.session.get_inputs()[0].name
        resolved_metadata_path = label_metadata_path or model_config.label_metadata_path
        self.metadata = _load_classifier_metadata(str(resolved_metadata_path)) if resolved_metadata_path else None

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

        frame_image = _open_image(frame)
        predictions: list[AttributePredictions] = []
        for vehicle_detection in vehicle_detections:
            crop = _crop_or_blank(
                frame_image,
                vehicle_detection.bbox,
                fallback_width=vehicle_detection.bbox.w,
                fallback_height=vehicle_detection.bbox.h,
            )
            tensor = _prepare_input(
                crop,
                input_width=self.model_config.input_width,
                input_height=self.model_config.input_height,
                normalization_mean=self.model_config.normalization_mean,
                normalization_std=self.model_config.normalization_std,
            )
            outputs = _session_output_map(self.session, self.session.run(None, {self.input_name: tensor}))
            if _supports_structured_classifier_outputs(set(outputs.keys())):
                color_index = _first_int(outputs["color_indices"])
                make_index = _first_int(outputs["make_indices"])
                color_label = (
                    self.model_config.color_labels[color_index]
                    if 0 <= color_index < len(self.model_config.color_labels)
                    else None
                )
                make_label = (
                    self.model_config.make_labels[make_index]
                    if 0 <= make_index < len(self.model_config.make_labels)
                    else None
                )
                predictions.append(
                    AttributePredictions.model_validate(
                        {
                            "color": color_label,
                            "color_confidence": _first_float(outputs["color_confidences"]),
                            "make": make_label,
                            "make_confidence": _first_float(outputs["make_confidences"]),
                            "model": _first_text(outputs["model_texts"]),
                            "model_confidence": _first_float(outputs["model_confidences"]),
                            "year": _first_text(outputs["year_texts"]),
                            "year_confidence": _first_float(outputs["year_confidences"]),
                        }
                    )
                )
                continue

            predictions.append(
                _attribute_prediction_from_logits(
                    outputs.get("logits", np.asarray([], dtype=np.float32)),
                    metadata=self.metadata,
                    model_config=self.model_config,
                )
            )
        return predictions


def build_onnx_adapter_bundle(
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

    if backend_values != {InferenceBackend.onnx} or ort is None:
        return None

    artifact_paths = [
        model_stack.resolve_artifact_path(model_stack.vehicle_detector.artifact_path),
        model_stack.resolve_artifact_path(model_stack.plate_detector.artifact_path),
        model_stack.resolve_artifact_path(model_stack.ocr.artifact_path),
    ]
    if model_stack.classifier is not None:
        artifact_paths.append(model_stack.resolve_artifact_path(model_stack.classifier.artifact_path))
        if model_stack.classifier.label_metadata_path:
            artifact_paths.append(model_stack.resolve_artifact_path(model_stack.classifier.label_metadata_path))
    if not all(_artifact_exists(path) for path in artifact_paths):
        return None

    classifier = None
    if model_stack.classifier is not None:
        classifier = OnnxClassifierAdapter(
            model_stack.classifier,
            artifact_path=model_stack.resolve_artifact_path(model_stack.classifier.artifact_path),
            label_metadata_path=(
                model_stack.resolve_artifact_path(model_stack.classifier.label_metadata_path)
                if model_stack.classifier.label_metadata_path
                else None
            ),
        )

    return ModelAdapterBundle(
        vehicle_detector=OnnxVehicleDetectorAdapter(
            model_stack.vehicle_detector,
            artifact_path=model_stack.resolve_artifact_path(model_stack.vehicle_detector.artifact_path),
        ),
        plate_detector=OnnxPlateDetectorAdapter(
            model_stack.plate_detector,
            artifact_path=model_stack.resolve_artifact_path(model_stack.plate_detector.artifact_path),
        ),
        ocr=OnnxOcrAdapter(
            model_stack.ocr,
            default_plate_text=default_plate_text,
            artifact_path=model_stack.resolve_artifact_path(model_stack.ocr.artifact_path),
        ),
        classifier=classifier,
    )
