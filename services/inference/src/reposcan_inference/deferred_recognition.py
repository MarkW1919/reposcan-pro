"""Deferred (post-scan) recognition runner.

Implements the execution half of Option B (see
docs/VEHICLE_RECOGNITION_PIPELINE_STATUS.md). Given a
``DeferredRecognitionConfig``, it composes the make/model primary, the
hierarchical re-rank specialists, and the optional year + color heads into a
single ``recognize`` call that returns one merged ``AttributePredictions`` per
vehicle detection.

Dispatch policy
---------------
1. Run make_model on every crop.
2. For each detection whose make_model prediction matches a re-rank head's
   ``trigger_classes``, re-run that specialist on the crop and take its
   make/model prediction instead.
3. Run year and color (if configured) on every crop and attach them.

The runner takes already-built classifier adapters (anything satisfying the
``ClassifierAdapter`` protocol), so the dispatch + merge logic is unit-testable
with lightweight stubs. ``build_deferred_recognition_runner`` wires real ONNX
adapters from a model-stack config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from reposcan_contracts.config.model import (
    DeferredRecognitionConfig,
    InferenceBackend,
    ModelStackConfig,
)
from reposcan_contracts.inference import AttributePredictions, VehicleDetection

from .adapters import ClassifierAdapter, InferenceFrame


@dataclass
class _RerankHead:
    name: str
    trigger_classes: frozenset[str]
    adapter: ClassifierAdapter


@dataclass
class DeferredRecognitionRunner:
    """Composes make/model + re-rank + year + color into one recognition pass."""

    make_model: ClassifierAdapter
    rerank_heads: list[_RerankHead] = field(default_factory=list)
    year: ClassifierAdapter | None = None
    color: ClassifierAdapter | None = None

    def recognize(
        self,
        frame: InferenceFrame,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        detections = list(vehicle_detections)
        if not detections:
            return []

        base = self.make_model.predict(frame, detections)
        # Defensive: make/model adapter should return one prediction per
        # detection. If it under-returns, pad with empty predictions so the
        # downstream merge stays index-aligned.
        merged = [base[i] if i < len(base) else AttributePredictions() for i in range(len(detections))]

        # Re-rank dispatch. For each head, gather the detections whose primary
        # make/model prediction is one of the head's trigger classes, run the
        # specialist on just those crops, and overwrite the make/model fields.
        for head in self.rerank_heads:
            indices = [
                i
                for i, pred in enumerate(merged)
                if pred.make is not None and pred.make in head.trigger_classes
            ]
            if not indices:
                continue
            subset = [detections[i] for i in indices]
            head_preds = head.adapter.predict(frame, subset)
            for slot, source_index in enumerate(indices):
                if slot >= len(head_preds):
                    break
                merged[source_index] = _apply_make_model(merged[source_index], head_preds[slot])

        # Parallel attribute heads run unconditionally on every crop.
        year_preds = self.year.predict(frame, detections) if self.year is not None else None
        color_preds = self.color.predict(frame, detections) if self.color is not None else None

        for i in range(len(detections)):
            if year_preds is not None and i < len(year_preds):
                merged[i] = _apply_year(merged[i], year_preds[i])
            if color_preds is not None and i < len(color_preds):
                merged[i] = _apply_color(merged[i], color_preds[i])

        return merged


def _apply_make_model(base: AttributePredictions, source: AttributePredictions) -> AttributePredictions:
    data = base.model_dump(by_alias=False)
    data["make"] = source.make
    data["make_confidence"] = source.make_confidence
    data["model_label"] = source.model_label
    data["model_confidence"] = source.model_confidence
    return AttributePredictions.model_validate(data)


def _apply_year(base: AttributePredictions, source: AttributePredictions) -> AttributePredictions:
    data = base.model_dump(by_alias=False)
    data["year"] = source.year
    data["year_confidence"] = source.year_confidence
    return AttributePredictions.model_validate(data)


def _apply_color(base: AttributePredictions, source: AttributePredictions) -> AttributePredictions:
    data = base.model_dump(by_alias=False)
    data["color"] = source.color
    data["color_confidence"] = source.color_confidence
    return AttributePredictions.model_validate(data)


def build_deferred_recognition_runner(
    model_stack: ModelStackConfig,
    *,
    providers: Sequence[str] | None = None,
) -> DeferredRecognitionRunner | None:
    """Wire a runner from a model-stack config's ``deferred_recognition`` block.

    Returns None when the stack has no deferred_recognition block, when any
    stage is not an ONNX backend, when onnxruntime is unavailable, or when any
    referenced artifact is missing — mirroring ``build_onnx_adapter_bundle``'s
    all-or-nothing contract so callers can cleanly fall back.
    """
    deferred = model_stack.deferred_recognition
    if deferred is None:
        return None

    # Import here to keep the dispatch/merge logic above import-light and
    # unit-testable without onnxruntime installed.
    from .onnx_adapters import OnnxClassifierAdapter, _artifact_exists, ort

    if ort is None:
        return None

    stages = _collect_classifier_stages(deferred)
    if any(stage.backend != InferenceBackend.onnx for _, stage in stages):
        return None

    artifact_paths = []
    for _, stage in stages:
        artifact_paths.append(model_stack.resolve_artifact_path(stage.artifact_path))
        if stage.label_metadata_path:
            artifact_paths.append(model_stack.resolve_artifact_path(stage.label_metadata_path))
    if not all(_artifact_exists(path) for path in artifact_paths):
        return None

    def _adapter(stage) -> OnnxClassifierAdapter:
        return OnnxClassifierAdapter(
            stage,
            artifact_path=model_stack.resolve_artifact_path(stage.artifact_path),
            label_metadata_path=(
                model_stack.resolve_artifact_path(stage.label_metadata_path)
                if stage.label_metadata_path
                else None
            ),
            providers=providers,
        )

    return DeferredRecognitionRunner(
        make_model=_adapter(deferred.make_model),
        rerank_heads=[
            _RerankHead(
                name=head.name,
                trigger_classes=frozenset(head.trigger_classes),
                adapter=_adapter(head.classifier),
            )
            for head in deferred.rerank_heads
        ],
        year=_adapter(deferred.year) if deferred.year is not None else None,
        color=_adapter(deferred.color) if deferred.color is not None else None,
    )


def _collect_classifier_stages(deferred: DeferredRecognitionConfig):
    stages = [("make_model", deferred.make_model)]
    for head in deferred.rerank_heads:
        stages.append((head.name, head.classifier))
    if deferred.year is not None:
        stages.append(("year", deferred.year))
    if deferred.color is not None:
        stages.append(("color", deferred.color))
    return stages
