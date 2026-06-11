"""Config-driven model adapter stubs for the inference service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from reposcan_contracts.config.model import ClassifierModelConfig, DetectorModelConfig, ModelStackConfig, OcrModelConfig
from reposcan_contracts.config.pipeline import PlateDetectionStrategy
from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import AttributePredictions, PlateDetection, VehicleDetection
from reposcan_contracts.detection import PlateCandidate

InferenceFrame = FrameEnvelope | PreparedFrame


class VehicleDetectorAdapter(Protocol):
    model_config: DetectorModelConfig

    def detect(self, frame: InferenceFrame) -> list[VehicleDetection]:
        ...


class PlateDetectorAdapter(Protocol):
    model_config: DetectorModelConfig

    def detect(
        self,
        frame: InferenceFrame,
        *,
        vehicle_detections: Sequence[VehicleDetection],
        strategy: PlateDetectionStrategy,
    ) -> list[PlateDetection]:
        ...


class OcrAdapter(Protocol):
    model_config: OcrModelConfig

    def recognize(self, frame: InferenceFrame, plate_detections: Sequence[PlateDetection]) -> list[PlateCandidate]:
        ...


class ClassifierAdapter(Protocol):
    model_config: ClassifierModelConfig

    def predict(
        self,
        frame: InferenceFrame,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        ...


@dataclass
class StaticVehicleDetectorAdapter:
    model_config: DetectorModelConfig
    outputs: list[VehicleDetection] = field(default_factory=list)

    def detect(self, frame: InferenceFrame) -> list[VehicleDetection]:
        return list(self.outputs)


@dataclass
class StaticPlateDetectorAdapter:
    model_config: DetectorModelConfig
    outputs: list[PlateDetection] = field(default_factory=list)

    def detect(
        self,
        frame: InferenceFrame,
        *,
        vehicle_detections: Sequence[VehicleDetection],
        strategy: PlateDetectionStrategy,
    ) -> list[PlateDetection]:
        if strategy == PlateDetectionStrategy.vehicle_crop and not vehicle_detections:
            return []
        return list(self.outputs)


@dataclass
class StaticOcrAdapter:
    model_config: OcrModelConfig
    outputs: list[PlateCandidate] = field(default_factory=list)

    def recognize(self, frame: InferenceFrame, plate_detections: Sequence[PlateDetection]) -> list[PlateCandidate]:
        if not plate_detections:
            return []
        return list(self.outputs)


@dataclass
class StaticClassifierAdapter:
    model_config: ClassifierModelConfig
    outputs: list[AttributePredictions] = field(default_factory=list)

    def predict(
        self,
        frame: InferenceFrame,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        if not vehicle_detections or not self.model_config.enabled:
            return []
        return list(self.outputs)


@dataclass
class ModelAdapterBundle:
    vehicle_detector: VehicleDetectorAdapter
    plate_detector: PlateDetectorAdapter
    ocr: OcrAdapter
    classifier: ClassifierAdapter | None = None

    @classmethod
    def noop_from_config(cls, model_stack: ModelStackConfig) -> "ModelAdapterBundle":
        classifier = None
        if model_stack.classifier is not None:
            classifier = StaticClassifierAdapter(model_stack.classifier, outputs=[])
        return cls(
            vehicle_detector=StaticVehicleDetectorAdapter(model_stack.vehicle_detector, outputs=[]),
            plate_detector=StaticPlateDetectorAdapter(model_stack.plate_detector, outputs=[]),
            ocr=StaticOcrAdapter(model_stack.ocr, outputs=[]),
            classifier=classifier,
        )
