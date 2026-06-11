"""Inference service skeleton."""

from __future__ import annotations

from time import perf_counter

from reposcan_contracts.config.loader import load_model_config, load_pipeline_config
from reposcan_contracts.config.model import ClassifierModelConfig, DetectorModelConfig, ModelStackConfig, OcrModelConfig
from reposcan_contracts.config.pipeline import PipelineConfig
from typing import Sequence

from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import AttributePredictions, InferenceCandidate, ModelVersions, VehicleDetection

from .adapters import ModelAdapterBundle
from .adapter_factory import build_runtime_adapter_bundle
from .deferred_recognition import DeferredRecognitionRunner, build_deferred_recognition_runner


def _model_version(model_config: DetectorModelConfig | OcrModelConfig | ClassifierModelConfig) -> str:
    return f"{model_config.name}|{model_config.backend.value}|{model_config.artifact_path}"


class InferenceService:
    def __init__(
        self,
        model_stack: ModelStackConfig,
        pipeline_config: PipelineConfig,
        adapters: ModelAdapterBundle,
        deferred_runner: DeferredRecognitionRunner | None = None,
    ) -> None:
        self.model_stack = model_stack
        self.pipeline_config = pipeline_config
        self.adapters = adapters
        # Optional post-scan recognition runner (make/model + re-rank + year +
        # color). Lives alongside, not inside, the real-time run() path: in the
        # dual-camera design the real-time camera does LPR only and this runs
        # against stored frames after the scan radius is exited.
        self.deferred_runner = deferred_runner

    @classmethod
    def from_config_paths(
        cls,
        *,
        model_config_path: str = "configs/models/example-model-stack.yaml",
        pipeline_config_path: str = "configs/pipelines/default-edge.yaml",
        adapters: ModelAdapterBundle | None = None,
        deferred_runner: DeferredRecognitionRunner | None = None,
    ) -> "InferenceService":
        model_stack = load_model_config(model_config_path)
        pipeline_config = load_pipeline_config(pipeline_config_path)
        configured_adapters = adapters
        if configured_adapters is None:
            configured_adapters = build_runtime_adapter_bundle(model_stack)
        resolved_deferred = deferred_runner
        if resolved_deferred is None:
            resolved_deferred = build_deferred_recognition_runner(model_stack)
        return cls(
            model_stack=model_stack,
            pipeline_config=pipeline_config,
            adapters=configured_adapters or ModelAdapterBundle.noop_from_config(model_stack),
            deferred_runner=resolved_deferred,
        )

    def model_versions(self) -> ModelVersions:
        classifier_version = None
        if self.model_stack.classifier is not None:
            classifier_version = _model_version(self.model_stack.classifier)
        return ModelVersions(
            vehicle_detector=_model_version(self.model_stack.vehicle_detector),
            plate_detector=_model_version(self.model_stack.plate_detector),
            ocr=_model_version(self.model_stack.ocr),
            classifier=classifier_version,
        )

    def run(self, frame: FrameEnvelope | PreparedFrame) -> InferenceCandidate:
        started = perf_counter()
        vehicle_detections = self.adapters.vehicle_detector.detect(frame)
        plate_detections = self.adapters.plate_detector.detect(
            frame,
            vehicle_detections=vehicle_detections,
            strategy=self.pipeline_config.plate_detection_strategy,
        )
        ocr_candidates = self.adapters.ocr.recognize(frame, plate_detections)

        attribute_predictions = []
        if self.adapters.classifier is not None:
            attribute_predictions = self.adapters.classifier.predict(frame, vehicle_detections)

        return InferenceCandidate(
            frame_id=frame.frame_id,
            camera_id=frame.camera_id,
            timestamp_utc=frame.timestamp_utc,
            vehicle_detections=vehicle_detections,
            plate_detections=plate_detections,
            ocr_candidates=ocr_candidates,
            attribute_predictions=attribute_predictions,
            model_versions=self.model_versions(),
            processing_latency_ms=max((perf_counter() - started) * 1000.0, 0.0),
        )

    def run_batch(self, frames: list[FrameEnvelope | PreparedFrame]) -> list[InferenceCandidate]:
        return [self.run(frame) for frame in frames]

    def has_deferred_recognition(self) -> bool:
        """True when a deferred recognition pipeline is wired and ready."""
        return self.deferred_runner is not None

    def recognize_deferred(
        self,
        frame: FrameEnvelope | PreparedFrame,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        """Run the deferred (post-scan) recognition pipeline on stored crops.

        Returns one merged AttributePredictions (make/model + re-rank +
        year + color) per supplied vehicle detection. Returns an empty list
        when no deferred_recognition pipeline is configured, so callers can
        invoke this unconditionally during post-scan enrichment.
        """
        if self.deferred_runner is None:
            return []
        return self.deferred_runner.recognize(frame, vehicle_detections)
