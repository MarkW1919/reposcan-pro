"""fast_alpr OCR adapter: decode mapping, confidence, and bundle wiring.

The real plate read is provided by fast-plate-ocr; these tests lock the adapter
contract (crop -> PlateCandidate, empty-read skip, confidence aggregation) with a
stubbed recognizer, plus the config-driven bundle + validation wiring against the
real end-to-end ALPR stack.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml
from PIL import Image

from reposcan_contracts.config.model import InferenceBackend, ModelStackConfig, OcrModelConfig
from reposcan_contracts.detection import BoundingBox
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.inference import PlateDetection

fast_alpr_mod = pytest.importorskip("reposcan_inference.fast_alpr_adapters")
from reposcan_inference.fast_alpr_adapters import FastPlateOcrAdapter, _confidence  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ALPR_CONFIG = REPO_ROOT / "configs" / "models" / "local-alpr-end2end.yaml"


def _ocr_config() -> OcrModelConfig:
    return OcrModelConfig.model_validate(
        {
            "name": "cct-xs-v2-global",
            "backend": "fast_alpr",
            "artifact_path": "runtime/models/plate-ocr/cct_xs_v2_global.onnx",
            "input_width": 128,
            "input_height": 64,
            "charset": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_",
            "confidence_threshold": 0.4,
        }
    )


def _frame(tmp_path: Path) -> FrameEnvelope:
    image_path = tmp_path / "frame.jpg"
    Image.new("RGB", (400, 200), color=(90, 90, 90)).save(image_path)
    return FrameEnvelope.model_validate(
        {
            "frame_id": "frm_alpr",
            "camera_id": "cam",
            "timestamp_utc": "2026-06-11T08:00:00Z",
            "frame_path": str(image_path),
            "frame_number": 0,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam", source_type=SourceType.file, resolution_w=400, resolution_h=200
            ).model_dump(mode="json"),
        }
    )


class _StubRecognizer:
    """Returns canned predictions in call order (stands in for LicensePlateRecognizer)."""

    def __init__(self, *predictions) -> None:
        self._queue = list(predictions)

    def run_one(self, image, return_confidence=False, remove_pad_char=True):  # noqa: ANN001
        return self._queue.pop(0)


def _adapter_with_stub(stub) -> FastPlateOcrAdapter:
    adapter = FastPlateOcrAdapter.__new__(FastPlateOcrAdapter)
    adapter.model_config = _ocr_config()
    adapter.recognizer = stub
    return adapter


def test_confidence_is_mean_over_decoded_chars():
    pred = SimpleNamespace(plate="ABC", char_probs=np.array([0.9, 0.8, 0.7, 0.1, 0.1], dtype=np.float32))
    # mean over the 3 decoded chars, padding slots ignored
    assert _confidence(pred, 3) == pytest.approx((0.9 + 0.8 + 0.7) / 3)


def test_confidence_handles_missing_probs():
    assert _confidence(SimpleNamespace(plate="X", char_probs=None), 1) == 0.0


def test_recognize_maps_plate_text_and_skips_empty(tmp_path):
    stub = _StubRecognizer(
        SimpleNamespace(plate="7ABC123", char_probs=np.full(7, 0.95, dtype=np.float32)),
        SimpleNamespace(plate="", char_probs=np.zeros(7, dtype=np.float32)),
    )
    adapter = _adapter_with_stub(stub)
    plates = [
        PlateDetection(bbox=BoundingBox(x=10, y=10, w=120, h=40), confidence=0.9, vehicle_index=0),
        PlateDetection(bbox=BoundingBox(x=200, y=80, w=120, h=40), confidence=0.8, vehicle_index=None),
    ]
    candidates = adapter.recognize(_frame(tmp_path), plates)

    assert len(candidates) == 1  # empty read skipped
    assert candidates[0].text == "7ABC123"
    assert candidates[0].confidence == pytest.approx(0.95)


def test_recognize_returns_empty_without_detections(tmp_path):
    adapter = _adapter_with_stub(_StubRecognizer())
    assert adapter.recognize(_frame(tmp_path), []) == []


# --- config-driven bundle + validation wiring (real models on disk) ----------


def _load_stack() -> ModelStackConfig:
    return ModelStackConfig.model_validate(yaml.safe_load(ALPR_CONFIG.read_text(encoding="utf-8")))


def test_alpr_config_declares_fast_alpr_ocr():
    stack = _load_stack()
    assert stack.ocr.backend == InferenceBackend.fast_alpr


@pytest.mark.skipif(
    not (REPO_ROOT / "runtime/models/plate-ocr/cct_xs_v2_global.onnx").exists(),
    reason="fast_alpr OCR model not staged under runtime/models/plate-ocr",
)
def test_validate_model_stack_marks_fast_alpr_ocr_ready():
    from reposcan_inference.validation import validate_model_stack

    report = _load_stack().__class__  # noqa: F841 - ensure import path resolves
    result = validate_model_stack(_load_stack())
    ocr_stage = next(s for s in result.stages if s.stage == "ocr")
    assert ocr_stage.backend == "fast_alpr"
    assert ocr_stage.ready is True, [i.message for i in ocr_stage.issues]


@pytest.mark.skipif(
    not (REPO_ROOT / "runtime/models/plate-ocr/cct_xs_v2_global.onnx").exists()
    or not (REPO_ROOT / "runtime/models/plate-detector/yolo-v9-t-384-license-plates-end2end.onnx").exists(),
    reason="real plate models not staged under runtime/models",
)
def test_build_bundle_wires_real_plate_detector_and_fast_alpr_ocr():
    from reposcan_inference.onnx_adapters import OnnxPlateDetectorAdapter, build_onnx_adapter_bundle

    bundle = build_onnx_adapter_bundle(_load_stack())
    assert bundle is not None
    assert isinstance(bundle.ocr, FastPlateOcrAdapter)
    assert isinstance(bundle.plate_detector, OnnxPlateDetectorAdapter)
