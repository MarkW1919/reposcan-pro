"""ONNX runtime adapters for the inference service."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

_logger = logging.getLogger(__name__)

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


def _center_xywh_to_relative_topleft_xywh(
    center_xywh: np.ndarray,
    *,
    input_width: int,
    input_height: int,
) -> np.ndarray:
    boxes = np.asarray(center_xywh, dtype=np.float32).reshape(-1, 4).copy()
    if boxes.size == 0:
        return boxes

    scale = np.asarray([input_width, input_height, input_width, input_height], dtype=np.float32)
    if float(np.nanmax(np.abs(boxes))) > 1.5:
        boxes = boxes / scale

    top_left = boxes.copy()
    top_left[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    top_left[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    top_left[:, 0] = np.clip(top_left[:, 0], 0.0, 1.0)
    top_left[:, 1] = np.clip(top_left[:, 1], 0.0, 1.0)
    top_left[:, 2] = np.clip(top_left[:, 2], 0.0, 1.0 - top_left[:, 0])
    top_left[:, 3] = np.clip(top_left[:, 3], 0.0, 1.0 - top_left[:, 1])
    return top_left


def _box_iou_xywh(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    box_x2 = box[0] + box[2]
    box_y2 = box[1] + box[3]
    boxes_x2 = boxes[:, 0] + boxes[:, 2]
    boxes_y2 = boxes[:, 1] + boxes[:, 3]
    inter_x1 = np.maximum(box[0], boxes[:, 0])
    inter_y1 = np.maximum(box[1], boxes[:, 1])
    inter_x2 = np.minimum(box_x2, boxes_x2)
    inter_y2 = np.minimum(box_y2, boxes_y2)
    inter_area = np.maximum(0.0, inter_x2 - inter_x1) * np.maximum(0.0, inter_y2 - inter_y1)
    box_area = max(float(box[2] * box[3]), 0.0)
    boxes_area = np.maximum(0.0, boxes[:, 2] * boxes[:, 3])
    union = box_area + boxes_area - inter_area
    return np.divide(inter_area, union, out=np.zeros_like(inter_area), where=union > 0.0)


def _nms_indices(boxes: np.ndarray, scores: np.ndarray, *, iou_threshold: float, limit: int = 300) -> list[int]:
    if boxes.size == 0 or scores.size == 0:
        return []
    order = np.argsort(scores)[::-1]
    keep: list[int] = []
    while order.size > 0 and len(keep) < limit:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        remaining = order[1:]
        ious = _box_iou_xywh(boxes[current], boxes[remaining])
        order = remaining[ious <= iou_threshold]
    return keep


def _looks_like_yolo_detector_output(output_map: dict[str, object]) -> bool:
    if len(output_map) != 1:
        return False
    output = np.asarray(next(iter(output_map.values())))
    if output.ndim != 3:
        return False
    shape = output.shape
    return shape[0] == 1 and (shape[1] >= 5 or shape[2] >= 5)


def _decode_yolo_detector_outputs(
    output_map: dict[str, object],
    model_config: DetectorModelConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = np.asarray(next(iter(output_map.values())), dtype=np.float32)
    if raw.ndim != 3 or raw.shape[0] != 1:
        return (
            np.empty((0, 4), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            np.empty((0,), dtype=np.int64),
        )

    predictions = raw[0]
    expected_channel_count = 4 + max(len(model_config.class_labels), 1)
    if predictions.shape[0] == expected_channel_count and predictions.shape[1] != expected_channel_count:
        predictions = predictions.T
    elif predictions.shape[0] < predictions.shape[1] and predictions.shape[0] >= 5:
        predictions = predictions.T
    if predictions.shape[1] < 5:
        return (
            np.empty((0, 4), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            np.empty((0,), dtype=np.int64),
        )

    boxes = _center_xywh_to_relative_topleft_xywh(
        predictions[:, :4],
        input_width=model_config.input_width,
        input_height=model_config.input_height,
    )
    class_scores = predictions[:, 4:]
    label_indices = np.argmax(class_scores, axis=1).astype(np.int64)
    scores = np.max(class_scores, axis=1).astype(np.float32)
    valid = (scores >= model_config.confidence_threshold) & (boxes[:, 2] > 0.0) & (boxes[:, 3] > 0.0)
    boxes = boxes[valid]
    scores = scores[valid]
    label_indices = label_indices[valid]
    if scores.size == 0:
        return boxes, scores, label_indices

    keep: list[int] = []
    for label_index in sorted(set(label_indices.tolist())):
        class_mask = label_indices == label_index
        class_positions = np.flatnonzero(class_mask)
        class_keep = _nms_indices(
            boxes[class_mask],
            scores[class_mask],
            iou_threshold=model_config.nms_iou_threshold,
        )
        keep.extend(int(class_positions[index]) for index in class_keep)

    keep = sorted(keep, key=lambda index: float(scores[index]), reverse=True)
    return boxes[keep], scores[keep], label_indices[keep]


def _looks_like_end2end_detector_output(output_map: dict[str, object]) -> bool:
    """Detect an "end2end" YOLO export: a single 2-D detection table.

    These exports (e.g. ``yolo-v9-t-384-license-plate-end2end``) run NMS inside
    the graph and emit one ``[num_detections, 6 or 7]`` tensor of already-filtered
    boxes, rather than the raw ``[1, 4+nc, anchors]`` grid the standard YOLO
    decoder consumes. Columns are pixel-space xyxy + score (+ optional leading
    batch index and a class column).
    """
    if len(output_map) != 1:
        return False
    output = np.asarray(next(iter(output_map.values())))
    if output.ndim != 2:
        return False
    return output.shape[1] in (6, 7)


def _decode_end2end_detector_outputs(
    output_map: dict[str, object],
    model_config: DetectorModelConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode an end2end detection table to relative top-left xywh + score + class.

    Supported column layouts (NMS already applied upstream):
      - 7 cols: ``[batch_idx, x1, y1, x2, y2, class_id, score]``
      - 6 cols: ``[x1, y1, x2, y2, score, class_id]``

    Coordinates are in input-resolution pixels, so we divide by the configured
    input size to get the relative boxes the rest of the pipeline expects.
    """
    raw = np.asarray(next(iter(output_map.values())), dtype=np.float32).reshape(-1, _end2end_cols(output_map))
    empty = (
        np.empty((0, 4), dtype=np.float32),
        np.empty((0,), dtype=np.float32),
        np.empty((0,), dtype=np.int64),
    )
    if raw.size == 0:
        return empty

    if raw.shape[1] == 7:
        xyxy = raw[:, 1:5]
        class_indices = raw[:, 5].astype(np.int64)
        scores = raw[:, 6].astype(np.float32)
    else:  # 6 columns
        xyxy = raw[:, 0:4]
        scores = raw[:, 4].astype(np.float32)
        class_indices = raw[:, 5].astype(np.int64)

    width = float(max(model_config.input_width, 1))
    height = float(max(model_config.input_height, 1))
    # Pixel-space coords (max magnitude >1.5) are normalized; already-relative exports pass through.
    if xyxy.size and float(np.nanmax(np.abs(xyxy))) > 1.5:
        xyxy = xyxy / np.asarray([width, height, width, height], dtype=np.float32)

    boxes = np.empty_like(xyxy)
    boxes[:, 0] = np.clip(xyxy[:, 0], 0.0, 1.0)
    boxes[:, 1] = np.clip(xyxy[:, 1], 0.0, 1.0)
    boxes[:, 2] = np.clip(xyxy[:, 2] - xyxy[:, 0], 0.0, 1.0 - boxes[:, 0])
    boxes[:, 3] = np.clip(xyxy[:, 3] - xyxy[:, 1], 0.0, 1.0 - boxes[:, 1])

    valid = (scores >= model_config.confidence_threshold) & (boxes[:, 2] > 0.0) & (boxes[:, 3] > 0.0)
    boxes = boxes[valid]
    scores = scores[valid]
    class_indices = class_indices[valid]
    if scores.size == 0:
        return empty
    order = np.argsort(scores)[::-1]
    return boxes[order], scores[order], class_indices[order]


def _end2end_cols(output_map: dict[str, object]) -> int:
    return int(np.asarray(next(iter(output_map.values()))).shape[1])


def _decode_detector_outputs(
    output_map: dict[str, object],
    model_config: DetectorModelConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if {"boxes_xywh", "scores", "label_indices"}.issubset(output_map):
        return (
            np.asarray(output_map["boxes_xywh"], dtype=np.float32).reshape(-1, 4),
            _flatten(output_map["scores"]).astype(np.float32),
            _flatten(output_map["label_indices"]).astype(np.int64),
        )
    if _looks_like_end2end_detector_output(output_map):
        return _decode_end2end_detector_outputs(output_map, model_config)
    if _looks_like_yolo_detector_output(output_map):
        return _decode_yolo_detector_outputs(output_map, model_config)
    return (
        np.empty((0, 4), dtype=np.float32),
        np.empty((0,), dtype=np.float32),
        np.empty((0,), dtype=np.int64),
    )


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


def _format_year_label(label: str | None) -> str | None:
    """Turn a year-bucket class label into a human-readable range.

    The year head emits class labels like ``bucket_2019_2022``; stored/displayed
    verbatim that is operator-hostile. Map them to ``2019-2022`` / ``2023+`` /
    ``pre-2010``. Non-bucket values (e.g. a literal ``2019``) pass through.
    """
    if not label or not label.startswith("bucket_"):
        return label
    body = label[len("bucket_"):]
    if body.startswith("pre_"):
        return f"pre-{body[len('pre_'):]}"
    if body.endswith("_plus"):
        return f"{body[: -len('_plus')]}+"
    parts = body.split("_")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}-{parts[1]}"
    return body.replace("_", " ")


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
        # Derive make/model/year from the canonical label as the source of
        # truth. Earlier exports baked make/model with a whitespace-only
        # parser, so a slug like "chevrolet_suburban" was stored as
        # make="chevrolet_suburban", model=None. Re-deriving here (build uses
        # the same parser) yields make="chevrolet", model="suburban" and is
        # robust to those stale sidecars; we only fall back to the baked
        # fields if the label itself yields nothing.
        make_label = None
        model_label = None
        year_label = None
        if record is not None:
            make_label, model_label, year_label = parse_vehicle_make_model_year(record.label)
            make_label = make_label or record.make
            model_label = model_label or record.model_label
            year_label = year_label or record.year
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
        year_label = _format_year_label(year_label)
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


_DEFAULT_PROVIDERS: tuple[str, ...] = ("CPUExecutionProvider",)


def _env_providers() -> tuple[str, ...] | None:
    raw = os.environ.get("REPOSCAN_ONNX_PROVIDERS")
    if not raw:
        return None
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(parts) if parts else None


def _filter_available(providers: Sequence[str]) -> tuple[str, ...]:
    runtime = _require_onnxruntime()
    available = set(runtime.get_available_providers())
    selected: list[str] = []
    skipped: list[str] = []
    for provider in providers:
        if provider in available:
            selected.append(provider)
        else:
            skipped.append(provider)
    if skipped:
        _logger.warning(
            "ONNX providers not available in this runtime, skipping: %s", ", ".join(skipped)
        )
    if not selected:
        if "CPUExecutionProvider" not in available:
            raise RuntimeError(
                "No usable ONNX execution providers found (not even CPUExecutionProvider)."
            )
        _logger.warning("Falling back to CPUExecutionProvider; no requested providers were available.")
        return ("CPUExecutionProvider",)
    if "CPUExecutionProvider" not in selected and "CPUExecutionProvider" in available:
        # Always keep CPU as the final safety net, mirroring onnxruntime's recommendation.
        selected.append("CPUExecutionProvider")
    return tuple(selected)


def _resolve_providers(providers: Sequence[str] | None) -> tuple[str, ...]:
    if providers is not None:
        return _filter_available(tuple(providers))
    env_providers = _env_providers()
    if env_providers is not None:
        return _filter_available(env_providers)
    return _filter_available(_DEFAULT_PROVIDERS)


def set_default_onnx_providers(providers: Sequence[str]) -> None:
    """Set the process-wide default ONNX provider chain.

    Falls back to CPU-only if no entries are valid on this runtime. Cached sessions
    built before this call still use whatever providers were active when they were
    created.
    """

    global _DEFAULT_PROVIDERS
    if not providers:
        raise ValueError("providers must not be empty")
    _DEFAULT_PROVIDERS = tuple(providers)


def get_default_onnx_providers() -> tuple[str, ...]:
    return _DEFAULT_PROVIDERS


@lru_cache(maxsize=16)
def _load_session_cached(path: str, providers_key: tuple[str, ...]):
    runtime = _require_onnxruntime()
    return runtime.InferenceSession(str(Path(path)), providers=list(providers_key))


def _load_session(path: str, providers: Sequence[str] | None = None):
    return _load_session_cached(path, _resolve_providers(providers))


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
    # Discriminate by config type, not stage name: deferred-recognition
    # classifier stages carry descriptive names (e.g. "deferred.make_model",
    # "deferred.rerank.jeep") but are still ClassifierModelConfig.
    if isinstance(model_config, ClassifierModelConfig):
        if _supports_structured_classifier_outputs(output_names):
            return issues
        if "logits" in output_names:
            if not isinstance(model_config, ClassifierModelConfig):
                issues.append("Logits-output classifier validation requires a ClassifierModelConfig.")
                return issues
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

    if stage in {"vehicle_detector", "plate_detector"} and _looks_like_yolo_detector_output(output_map):
        return issues

    missing = sorted(required_outputs[stage] - output_names)
    if missing:
        issues.append(f"Missing required outputs for {stage}: {', '.join(missing)}")
    return issues


class OnnxVehicleDetectorAdapter:
    def __init__(
        self,
        model_config: DetectorModelConfig,
        *,
        artifact_path: str | Path | None = None,
        providers: Sequence[str] | None = None,
    ) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path, providers)
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
        boxes, scores, label_indices = _decode_detector_outputs(outputs, self.model_config)

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
    def __init__(
        self,
        model_config: DetectorModelConfig,
        *,
        artifact_path: str | Path | None = None,
        providers: Sequence[str] | None = None,
    ) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path, providers)
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
                boxes, scores, _ = _decode_detector_outputs(outputs, self.model_config)
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
        boxes, scores, _ = _decode_detector_outputs(outputs, self.model_config)
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
        providers: Sequence[str] | None = None,
    ) -> None:
        self.model_config = model_config
        self.default_plate_text = default_plate_text
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path, providers)
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
        providers: Sequence[str] | None = None,
    ) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path or model_config.artifact_path)
        self.session = _load_session(self.artifact_path, providers)
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
    providers: Sequence[str] | None = None,
) -> ModelAdapterBundle | None:
    # Detectors + classifier must be ONNX; the OCR stage may be ONNX or the
    # fast_alpr backend (fast-plate-ocr owns its own model + decode). This lets a
    # real plate detector compose with a real plate reader in one ONNX bundle.
    detector_backends = {
        model_stack.vehicle_detector.backend,
        model_stack.plate_detector.backend,
    }
    if model_stack.classifier is not None:
        detector_backends.add(model_stack.classifier.backend)

    if detector_backends != {InferenceBackend.onnx} or ort is None:
        return None
    if model_stack.ocr.backend not in (InferenceBackend.onnx, InferenceBackend.fast_alpr):
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
            providers=providers,
        )

    if model_stack.ocr.backend == InferenceBackend.fast_alpr:
        # Lazy import avoids a circular dependency (fast_alpr_adapters imports
        # crop/open helpers from this module).
        from .fast_alpr_adapters import build_fast_alpr_ocr_adapter

        ocr_adapter = build_fast_alpr_ocr_adapter(model_stack, providers=providers)
        if ocr_adapter is None:
            return None
    else:
        ocr_adapter = OnnxOcrAdapter(
            model_stack.ocr,
            default_plate_text=default_plate_text,
            artifact_path=model_stack.resolve_artifact_path(model_stack.ocr.artifact_path),
            providers=providers,
        )

    return ModelAdapterBundle(
        vehicle_detector=OnnxVehicleDetectorAdapter(
            model_stack.vehicle_detector,
            artifact_path=model_stack.resolve_artifact_path(model_stack.vehicle_detector.artifact_path),
            providers=providers,
        ),
        plate_detector=OnnxPlateDetectorAdapter(
            model_stack.plate_detector,
            artifact_path=model_stack.resolve_artifact_path(model_stack.plate_detector.artifact_path),
            providers=providers,
        ),
        ocr=ocr_adapter,
        classifier=classifier,
    )
