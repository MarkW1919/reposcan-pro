"""OCR adapter backed by the fast-plate-ocr ``LicensePlateRecognizer``.

This wires a real, pretrained license-plate OCR model into the inference
service's OCR slot. Unlike :class:`OnnxOcrAdapter` — which runs a bespoke ONNX
graph and expects ``texts``/``confidences`` named outputs — fast-plate-ocr ships
its own ONNX model plus a ``plate_config`` and owns the full pipeline
(letterbox/resize, color mode, CTC-style multi-head decode over its alphabet).
So we wrap the library rather than feed its model through the generic decoder.

Loading is fully local/offline: the adapter takes an ``onnx_model_path`` and a
sibling ``plate_config`` file (staged under ``runtime/models/plate-ocr/``), so
no network/hub access is needed at runtime — required for the edge-first,
no-internet operating constraint. ``providers`` is passed straight through so
the same adapter TensorRT/CUDA-accelerates on the Jetson.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np

from reposcan_contracts.config.model import InferenceBackend, ModelStackConfig, OcrModelConfig
from reposcan_contracts.detection import PlateCandidate
from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import PlateDetection

from .onnx_adapters import _crop_or_blank, _open_image
from .runtime_adapters import _frame_sidecar

_logger = logging.getLogger(__name__)

InferenceFrame = FrameEnvelope | PreparedFrame

try:  # pragma: no cover - import guard exercised only when the lib is absent
    from fast_plate_ocr import LicensePlateRecognizer
except Exception:  # noqa: BLE001 - any import failure means the backend is unusable
    LicensePlateRecognizer = None  # type: ignore[assignment]


def fast_alpr_available() -> bool:
    return LicensePlateRecognizer is not None


def _resolve_plate_config_path(onnx_path: Path) -> Path | None:
    """Find the plate_config YAML that pairs with an OCR onnx artifact.

    fast-plate-ocr names it ``<stem>_plate_config.yaml`` (hub convention); we
    also accept ``<stem>.yaml`` and a lone ``plate_config.yaml`` in the dir.
    """
    candidates = [
        onnx_path.with_name(f"{onnx_path.stem}_plate_config.yaml"),
        onnx_path.with_name(f"{onnx_path.stem}.yaml"),
        onnx_path.with_name("plate_config.yaml"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class FastPlateOcrAdapter:
    """Reads plate text from detected plate regions via fast-plate-ocr."""

    def __init__(
        self,
        model_config: OcrModelConfig,
        *,
        onnx_model_path: str | Path,
        plate_config_path: str | Path | None = None,
        providers: Sequence[str] | None = None,
    ) -> None:
        if LicensePlateRecognizer is None:
            raise RuntimeError("fast-plate-ocr is not installed in the active Python environment.")
        self.model_config = model_config
        self.onnx_model_path = Path(onnx_model_path)
        resolved_config = (
            Path(plate_config_path) if plate_config_path else _resolve_plate_config_path(self.onnx_model_path)
        )
        if resolved_config is None or not resolved_config.exists():
            raise FileNotFoundError(
                f"fast-plate-ocr plate_config not found for '{self.onnx_model_path}'. "
                "Expected a '<stem>_plate_config.yaml' sibling."
            )
        self.plate_config_path = resolved_config
        self.recognizer = LicensePlateRecognizer(
            onnx_model_path=str(self.onnx_model_path),
            plate_config_path=str(self.plate_config_path),
            providers=list(providers) if providers else None,
        )

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
            rgb = np.asarray(crop.convert("RGB"), dtype=np.uint8)
            prediction = self.recognizer.run_one(rgb, return_confidence=True)
            text = (prediction.plate or "").strip()
            if not text:
                continue  # no readable plate in this region
            candidates.append(PlateCandidate(text=text, confidence=_confidence(prediction, len(text))))
        return candidates


def _confidence(prediction, text_len: int) -> float:
    """Mean per-character probability over the decoded (non-pad) characters."""
    probs = getattr(prediction, "char_probs", None)
    if probs is None:
        return 0.0
    arr = np.asarray(probs, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return 0.0
    usable = arr[:text_len] if 0 < text_len <= arr.size else arr
    return float(np.clip(np.mean(usable), 0.0, 1.0))


def build_fast_alpr_ocr_adapter(
    model_stack: ModelStackConfig,
    *,
    providers: Sequence[str] | None = None,
) -> FastPlateOcrAdapter | None:
    """Build a FastPlateOcrAdapter from a stack whose OCR stage uses fast_alpr.

    Returns ``None`` (rather than raising) when the OCR stage is not fast_alpr,
    the library is unavailable, or the model artifact is missing — mirroring the
    all-or-nothing contract of ``build_onnx_adapter_bundle`` so callers can try
    backends in order.
    """
    ocr = model_stack.ocr
    if ocr.backend != InferenceBackend.fast_alpr or LicensePlateRecognizer is None:
        return None
    onnx_path = Path(model_stack.resolve_artifact_path(ocr.artifact_path))
    if not onnx_path.exists():
        _logger.warning("fast_alpr OCR artifact '%s' not found.", onnx_path)
        return None
    return FastPlateOcrAdapter(ocr, onnx_model_path=onnx_path, providers=providers)
