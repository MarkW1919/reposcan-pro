"""TensorRT engine adapters for the inference service.

These adapters use the NVIDIA TensorRT Python bindings (``tensorrt`` and
``pycuda``). They become active only when the bindings are importable AND every
stage in the model stack uses ``backend=tensorrt``. On CPU-only workstations the
factory returns ``None`` so the higher-level builder can fall back to ONNX or
log a clear error. Hardware-bound execution paths must be re-validated against
the target Jetson once the device is on hand; the structure here exists so the
runtime never silently falls through to demo adapters when the deployment
profile demands tensorrt.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

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
from .onnx_adapters import (
    _attribute_prediction_from_logits,
    _crop_or_blank,
    _decode_detector_outputs,
    _full_image_or_blank,
    _load_classifier_metadata,
    _open_image,
    _prepare_input,
    _relative_bbox_to_absolute,
    _supports_structured_classifier_outputs,
    _first_int,
    _first_float,
    _first_text,
)
from .runtime_adapters import _frame_sidecar

InferenceFrame = FrameEnvelope | PreparedFrame

_logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised only on Jetson hardware
    import tensorrt as trt  # type: ignore
    import pycuda.autoinit  # type: ignore  # noqa: F401  (initializes CUDA context)
    import pycuda.driver as cuda  # type: ignore
except Exception:  # noqa: BLE001 - any failure means TRT bindings unusable
    trt = None  # type: ignore[assignment]
    cuda = None  # type: ignore[assignment]


def tensorrt_available() -> bool:
    return trt is not None and cuda is not None


class TensorRTUnavailableError(RuntimeError):
    """Raised when TensorRT bindings are required but unavailable on this host."""


class _TrtEngineRunner:  # pragma: no cover - hardware-only
    def __init__(self, engine_path: Path) -> None:
        if not tensorrt_available():
            raise TensorRTUnavailableError(
                "TensorRT bindings (tensorrt + pycuda) are not installed on this host."
            )
        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as handle, trt.Runtime(logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(handle.read())
        if self.engine is None:
            raise TensorRTUnavailableError(f"Failed to deserialize TensorRT engine '{engine_path}'.")
        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()
        self._bindings: list[int] = []
        self._buffers: list[tuple[np.ndarray, cuda.DeviceAllocation]] = []
        for binding_idx in range(self.engine.num_bindings):
            shape = tuple(self.engine.get_binding_shape(binding_idx))
            dtype = trt.nptype(self.engine.get_binding_dtype(binding_idx))
            host_mem = np.empty(shape, dtype=dtype)
            device_mem = cuda.mem_alloc(host_mem.nbytes)
            self._bindings.append(int(device_mem))
            self._buffers.append((host_mem, device_mem))

    def infer(self, input_array: np.ndarray) -> dict[str, np.ndarray]:
        host_input, device_input = self._buffers[0]
        np.copyto(host_input, input_array.reshape(host_input.shape))
        cuda.memcpy_htod_async(device_input, host_input, self.stream)
        self.context.execute_async_v2(bindings=self._bindings, stream_handle=self.stream.handle)
        outputs: dict[str, np.ndarray] = {}
        for binding_idx in range(1, self.engine.num_bindings):
            host_mem, device_mem = self._buffers[binding_idx]
            cuda.memcpy_dtoh_async(host_mem, device_mem, self.stream)
            outputs[self.engine.get_binding_name(binding_idx)] = host_mem
        self.stream.synchronize()
        return outputs


@lru_cache(maxsize=8)
def _load_engine(path: str) -> _TrtEngineRunner:  # pragma: no cover - hardware-only
    return _TrtEngineRunner(Path(path))


class TrtVehicleDetectorAdapter:  # pragma: no cover - hardware-only
    def __init__(self, model_config: DetectorModelConfig, *, artifact_path: str | Path) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path)
        self.engine = _load_engine(self.artifact_path)

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
        outputs = self.engine.infer(tensor)
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


class TrtPlateDetectorAdapter:  # pragma: no cover - hardware-only
    def __init__(self, model_config: DetectorModelConfig, *, artifact_path: str | Path) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path)
        self.engine = _load_engine(self.artifact_path)

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
                outputs = self.engine.infer(tensor)
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
        outputs = self.engine.infer(tensor)
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


class TrtOcrAdapter:  # pragma: no cover - hardware-only
    def __init__(self, model_config: OcrModelConfig, *, artifact_path: str | Path, default_plate_text: str | None = None) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path)
        self.engine = _load_engine(self.artifact_path)
        self.default_plate_text = default_plate_text

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
            outputs = self.engine.infer(tensor)
            text = self.default_plate_text or _first_text(outputs.get("texts")) or "UNKNOWN"
            confidence = max(self.model_config.confidence_threshold, _first_float(outputs.get("confidences", np.zeros(1, dtype=np.float32))))
            candidates.append(PlateCandidate(text=text, confidence=confidence))
        return candidates


class TrtClassifierAdapter:  # pragma: no cover - hardware-only
    def __init__(
        self,
        model_config: ClassifierModelConfig,
        *,
        artifact_path: str | Path,
        label_metadata_path: str | Path | None = None,
    ) -> None:
        self.model_config = model_config
        self.artifact_path = str(artifact_path)
        self.engine = _load_engine(self.artifact_path)
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
            outputs = self.engine.infer(tensor)
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


def build_tensorrt_adapter_bundle(
    model_stack: ModelStackConfig,
    *,
    default_plate_text: str | None = None,
) -> ModelAdapterBundle | None:
    """Build TRT-engine-backed adapters when every stage uses backend=tensorrt.

    Returns ``None`` when:
    - any stage has a non-tensorrt backend, or
    - the host lacks the NVIDIA TensorRT Python bindings (CPU dev workstations), or
    - one or more engine artifacts are missing on disk.

    Hardware-bound execution paths inside the TRT adapters are exercised on the
    target Jetson; that wiring is intentionally separate from the CPU-only test
    suite that runs in CI.
    """

    backend_values = {
        model_stack.vehicle_detector.backend,
        model_stack.plate_detector.backend,
        model_stack.ocr.backend,
    }
    if model_stack.classifier is not None:
        backend_values.add(model_stack.classifier.backend)
    if backend_values != {InferenceBackend.tensorrt}:
        return None
    if not tensorrt_available():
        _logger.warning(
            "Model stack '%s' requires TensorRT, but the tensorrt/pycuda Python bindings are not available on this host.",
            model_stack.stack_name,
        )
        return None

    artifact_paths = [
        model_stack.resolve_artifact_path(model_stack.vehicle_detector.artifact_path),
        model_stack.resolve_artifact_path(model_stack.plate_detector.artifact_path),
        model_stack.resolve_artifact_path(model_stack.ocr.artifact_path),
    ]
    if model_stack.classifier is not None:
        artifact_paths.append(model_stack.resolve_artifact_path(model_stack.classifier.artifact_path))
    if not all(Path(path).exists() for path in artifact_paths):
        _logger.warning(
            "Model stack '%s' has missing TensorRT engine artifacts; cannot build TRT bundle.",
            model_stack.stack_name,
        )
        return None

    classifier = None
    if model_stack.classifier is not None:
        classifier = TrtClassifierAdapter(
            model_stack.classifier,
            artifact_path=model_stack.resolve_artifact_path(model_stack.classifier.artifact_path),
            label_metadata_path=(
                model_stack.resolve_artifact_path(model_stack.classifier.label_metadata_path)
                if model_stack.classifier.label_metadata_path
                else None
            ),
        )

    return ModelAdapterBundle(
        vehicle_detector=TrtVehicleDetectorAdapter(
            model_stack.vehicle_detector,
            artifact_path=model_stack.resolve_artifact_path(model_stack.vehicle_detector.artifact_path),
        ),
        plate_detector=TrtPlateDetectorAdapter(
            model_stack.plate_detector,
            artifact_path=model_stack.resolve_artifact_path(model_stack.plate_detector.artifact_path),
        ),
        ocr=TrtOcrAdapter(
            model_stack.ocr,
            artifact_path=model_stack.resolve_artifact_path(model_stack.ocr.artifact_path),
            default_plate_text=default_plate_text,
        ),
        classifier=classifier,
    )
