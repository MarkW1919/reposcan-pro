"""Lock in the deploy-aware ONNX/TRT provider selection so the Jetson rollout
never silently regresses to CPU-only inference, and so production paths refuse
to start when no real adapter bundle can be built."""

from __future__ import annotations

import importlib

import pytest

from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.config.model import (
    ClassifierModelConfig,
    DetectorModelConfig,
    InferenceBackend,
    ModelStackConfig,
    OcrModelConfig,
)
from reposcan_inference import (
    build_deployment_runtime_adapter_bundle,
    build_runtime_adapter_bundle,
    get_default_onnx_providers,
    set_default_onnx_providers,
)
from reposcan_inference.adapter_factory import _providers_for_deployment
from reposcan_inference.onnx_adapters import _filter_available, _resolve_providers


def _detector_config(path: str) -> DetectorModelConfig:
    return DetectorModelConfig.model_validate(
        {
            "name": "detector",
            "backend": "tensorrt",
            "artifact_path": path,
            "input_width": 320,
            "input_height": 320,
            "class_labels": ["vehicle"],
            "confidence_threshold": 0.4,
            "nms_iou_threshold": 0.5,
        }
    )


def _ocr_config(path: str) -> OcrModelConfig:
    return OcrModelConfig.model_validate(
        {
            "name": "ocr",
            "backend": "tensorrt",
            "artifact_path": path,
            "input_width": 94,
            "input_height": 24,
            "charset": "0123456789ABC",
            "beam_width": 5,
            "confidence_threshold": 0.5,
        }
    )


def _classifier_config(path: str) -> ClassifierModelConfig:
    return ClassifierModelConfig.model_validate(
        {
            "name": "classifier",
            "backend": "tensorrt",
            "artifact_path": path,
            "input_width": 224,
            "input_height": 224,
            "color_labels": ["white", "black"],
            "make_labels": ["toyota", "ford"],
            "enabled": True,
        }
    )


def _tensorrt_stack(tmp_path) -> ModelStackConfig:
    artifact_dir = tmp_path / "engines"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return ModelStackConfig.model_validate(
        {
            "stack_name": "tensorrt-test",
            "path_base": "config_dir",
            "vehicle_detector": _detector_config(str(artifact_dir / "vehicle.engine")),
            "plate_detector": _detector_config(str(artifact_dir / "plate.engine")),
            "ocr": _ocr_config(str(artifact_dir / "ocr.engine")),
            "classifier": _classifier_config(str(artifact_dir / "classifier.engine")),
        }
    )


def _jetson_deployment_config() -> DeploymentConfig:
    return DeploymentConfig.model_validate(
        {
            "deployment_name": "jetson-test",
            "target_hardware": "jetson_orin_nano_super",
            "runtime": {
                "required_backend": "tensorrt",
                "target_runtime": "tensorrt",
                "required_path_base": "config_dir",
            },
        }
    )


def _cpu_deployment_config() -> DeploymentConfig:
    return DeploymentConfig.model_validate(
        {
            "deployment_name": "cpu-test",
            "target_hardware": "cpu",
            "runtime": {"target_runtime": "onnxruntime"},
        }
    )


def test_default_onnx_providers_can_be_overridden_and_filter_to_available():
    original = get_default_onnx_providers()
    try:
        set_default_onnx_providers(["NotARealProvider", "CPUExecutionProvider"])
        # Resolve filters out unavailable providers and always keeps CPU as a tail.
        resolved = _resolve_providers(None)
        assert resolved == ("CPUExecutionProvider",)
    finally:
        set_default_onnx_providers(list(original))


def test_resolve_providers_explicit_request_respects_caller():
    resolved = _resolve_providers(["CPUExecutionProvider"])
    assert resolved == ("CPUExecutionProvider",)


def test_filter_available_raises_when_runtime_has_no_providers(monkeypatch):
    import reposcan_inference.onnx_adapters as onnx_adapters_module

    class _StubRuntime:
        @staticmethod
        def get_available_providers():
            return []

    monkeypatch.setattr(onnx_adapters_module, "ort", _StubRuntime)
    with pytest.raises(RuntimeError):
        _filter_available(["CUDAExecutionProvider"])


def test_providers_for_deployment_jetson_returns_tensorrt_chain():
    deployment = _jetson_deployment_config()
    stack = _tensorrt_stack(tmp_path=__import__("pathlib").Path("/tmp"))
    chain = _providers_for_deployment(deployment, stack)
    assert chain == (
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    )


def test_providers_for_deployment_cpu_falls_through_to_default():
    deployment = _cpu_deployment_config()
    stack = _tensorrt_stack(tmp_path=__import__("pathlib").Path("/tmp"))
    assert _providers_for_deployment(deployment, stack) is None


def test_tensorrt_stack_without_bindings_returns_none(tmp_path):
    """When the TRT bindings aren't installed (CPU dev box, CI), the factory
    must return None so the production path can refuse to start with placeholder
    adapters instead of silently emitting fake plate reads."""

    stack = _tensorrt_stack(tmp_path)
    # Touch the engine files so artifact-existence is not the blocker.
    for engine_path in [
        stack.vehicle_detector.artifact_path,
        stack.plate_detector.artifact_path,
        stack.ocr.artifact_path,
        stack.classifier.artifact_path,
    ]:
        __import__("pathlib").Path(engine_path).write_bytes(b"engine-stub")

    assert build_runtime_adapter_bundle(stack) is None


def test_deployment_aware_bundle_returns_none_for_tensorrt_without_bindings(tmp_path):
    stack = _tensorrt_stack(tmp_path)
    deployment = _jetson_deployment_config()
    assert build_deployment_runtime_adapter_bundle(stack, deployment) is None
