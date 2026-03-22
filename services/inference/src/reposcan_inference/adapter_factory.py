"""Inference adapter factory helpers."""

from __future__ import annotations

from reposcan_contracts.config.model import ModelStackConfig

from .adapters import ModelAdapterBundle
from .onnx_adapters import build_onnx_adapter_bundle
from .runtime_adapters import build_builtin_runtime_adapter_bundle


def build_runtime_adapter_bundle(
    model_stack: ModelStackConfig,
    *,
    default_plate_text: str | None = None,
) -> ModelAdapterBundle | None:
    return (
        build_builtin_runtime_adapter_bundle(model_stack, default_plate_text=default_plate_text)
        or build_onnx_adapter_bundle(model_stack, default_plate_text=default_plate_text)
    )
