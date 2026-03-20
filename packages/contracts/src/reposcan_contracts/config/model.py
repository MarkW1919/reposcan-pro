"""Model stack configuration schema.

Loaded from configs/models/*.yaml by the inference service.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InferenceBackend(str, Enum):
    onnx = "onnx"
    tensorrt = "tensorrt"
    pytorch = "pytorch"


class DetectorModelConfig(BaseModel):
    """Config for a YOLO-style detection model (vehicle or plate detector)."""

    name: str = Field(..., description="Human-readable model name")
    backend: InferenceBackend = InferenceBackend.onnx
    artifact_path: str = Field(..., description="Path to model artifact relative to repo root")
    input_width: int = Field(..., gt=0)
    input_height: int = Field(..., gt=0)
    normalization_mean: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    normalization_std: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    class_labels: list[str] = Field(default_factory=list)
    confidence_threshold: float = Field(0.4, ge=0.0, le=1.0)
    nms_iou_threshold: float = Field(0.5, ge=0.0, le=1.0)


class OcrModelConfig(BaseModel):
    """Config for the OCR model (CTC-based LPR network)."""

    name: str
    backend: InferenceBackend = InferenceBackend.onnx
    artifact_path: str
    input_width: int = Field(..., gt=0)
    input_height: int = Field(..., gt=0)
    charset: str = Field(..., description="Character set recognized by the model")
    beam_width: int = Field(5, gt=0, description="CTC beam search width")
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)


class ClassifierModelConfig(BaseModel):
    """Config for the vehicle attribute classifier (color, make/model)."""

    name: str
    backend: InferenceBackend = InferenceBackend.onnx
    artifact_path: str
    input_width: int = Field(..., gt=0)
    input_height: int = Field(..., gt=0)
    normalization_mean: list[float] = Field(default_factory=lambda: [0.485, 0.456, 0.406])
    normalization_std: list[float] = Field(default_factory=lambda: [0.229, 0.224, 0.225])
    color_labels: list[str] = Field(default_factory=list)
    make_labels: list[str] = Field(default_factory=list)
    enabled: bool = True


class ModelStackConfig(BaseModel):
    """Complete model stack configuration loaded from configs/models/*.yaml."""

    stack_name: str = Field(..., description="Identifier for this model stack")
    description: Optional[str] = None
    vehicle_detector: DetectorModelConfig
    plate_detector: DetectorModelConfig
    ocr: OcrModelConfig
    classifier: Optional[ClassifierModelConfig] = Field(
        None, description="Classifier is optional — disable for inference-only deployments"
    )
