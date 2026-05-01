"""Inference adapter factory helpers."""

from __future__ import annotations

import logging
from typing import Sequence

from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.config.model import InferenceBackend, ModelStackConfig

from .adapters import ModelAdapterBundle
from .onnx_adapters import build_onnx_adapter_bundle
from .runtime_adapters import build_builtin_runtime_adapter_bundle
from .trt_adapters import build_tensorrt_adapter_bundle, tensorrt_available

_logger = logging.getLogger(__name__)


class RuntimeAdapterUnavailableError(RuntimeError):
    """Raised when a model stack declares a backend but no real adapter can be built.

    This is the explicit, loud signal the production runtime should rely on
    instead of silently falling back to demo adapters that emit fake plate
    reads. The capture-to-storage path has no business running when the model
    stack the operator configured cannot actually be executed on this host.
    """


def build_runtime_adapter_bundle(
    model_stack: ModelStackConfig,
    *,
    default_plate_text: str | None = None,
    onnx_providers: Sequence[str] | None = None,
) -> ModelAdapterBundle | None:
    """Build the best available real adapter bundle for ``model_stack``.

    Selection rules:
    - ``backend == builtin`` for every stage → builtin demo-grade artifact bundle.
    - ``backend == tensorrt`` for every stage → TensorRT engine bundle when the
      Jetson python bindings are present and the engine artifacts exist on disk.
    - ``backend == onnx`` for every stage with all artifacts present → ONNX
      Runtime bundle, optionally with caller-supplied execution providers
      (e.g. ``["TensorrtExecutionProvider", "CUDAExecutionProvider", ...]``).

    Returns ``None`` when no real adapter bundle can be assembled. Callers in
    production paths should refuse to start when this happens; demo/test
    helpers may opt in to the demo fallback explicitly.
    """

    builtin = build_builtin_runtime_adapter_bundle(model_stack, default_plate_text=default_plate_text)
    if builtin is not None:
        return builtin

    trt_bundle = build_tensorrt_adapter_bundle(model_stack, default_plate_text=default_plate_text)
    if trt_bundle is not None:
        return trt_bundle

    return build_onnx_adapter_bundle(
        model_stack,
        default_plate_text=default_plate_text,
        providers=onnx_providers,
    )


def build_deployment_runtime_adapter_bundle(
    model_stack: ModelStackConfig,
    deployment: DeploymentConfig,
    *,
    default_plate_text: str | None = None,
) -> ModelAdapterBundle | None:
    """Build a real adapter bundle informed by deployment runtime requirements.

    When the deployment profile sets a ``required_backend`` other than what the
    model stack actually carries, this still tries to build the model stack's
    declared backend so the operator gets a clear runtime-vs-deployment
    mismatch instead of a silent CPU fallback. ``validate_deployment_runtime_bundle``
    is the right place to lock down profile compliance before the runtime even
    starts; this helper just translates the profile into provider hints.
    """

    providers = _providers_for_deployment(deployment, model_stack)
    bundle = build_runtime_adapter_bundle(
        model_stack,
        default_plate_text=default_plate_text,
        onnx_providers=providers,
    )
    if bundle is None:
        _logger.error(
            "No usable inference adapter bundle for stack '%s' under deployment '%s'.",
            model_stack.stack_name,
            deployment.deployment_name,
        )
    return bundle


def _providers_for_deployment(
    deployment: DeploymentConfig,
    model_stack: ModelStackConfig,
) -> tuple[str, ...] | None:
    runtime_cfg = deployment.runtime
    target = (runtime_cfg.target_runtime or "").lower()
    required = runtime_cfg.required_backend

    # The deployment-side execution-provider chain ramps from highest accel to
    # CPU so the runtime never refuses to start; ONNX Runtime will skip any
    # provider that is not installed and log it via _filter_available.
    if target == "tensorrt" or required == InferenceBackend.tensorrt:
        return ("TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider")
    if target in {"onnxruntime-cuda", "cuda"} or required == InferenceBackend.pytorch:
        return ("CUDAExecutionProvider", "CPUExecutionProvider")
    if target in {"onnxruntime", "onnxruntime-cpu", "cpu", ""}:
        return None  # honor REPOSCAN_ONNX_PROVIDERS env or the global default
    return None


__all__ = [
    "build_runtime_adapter_bundle",
    "build_deployment_runtime_adapter_bundle",
    "RuntimeAdapterUnavailableError",
    "tensorrt_available",
]
