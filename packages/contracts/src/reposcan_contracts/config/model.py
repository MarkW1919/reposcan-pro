"""Model stack configuration schema.

Loaded from configs/models/*.yaml by the inference service.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, PrivateAttr


class InferenceBackend(str, Enum):
    builtin = "builtin"
    onnx = "onnx"
    tensorrt = "tensorrt"
    pytorch = "pytorch"


class ArtifactPathBase(str, Enum):
    repo_root = "repo_root"
    config_dir = "config_dir"


class DetectorModelConfig(BaseModel):
    """Config for a YOLO-style detection model (vehicle or plate detector)."""

    name: str = Field(..., description="Human-readable model name")
    backend: InferenceBackend = InferenceBackend.onnx
    artifact_path: str = Field(..., description="Path to model artifact resolved according to the stack path_base")
    artifact_manifest_path: str | None = Field(None, description="Optional path to the promoted artifact manifest")
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
    artifact_path: str = Field(..., description="Path to model artifact resolved according to the stack path_base")
    artifact_manifest_path: str | None = Field(None, description="Optional path to the promoted artifact manifest")
    input_width: int = Field(..., gt=0)
    input_height: int = Field(..., gt=0)
    charset: str = Field(..., description="Character set recognized by the model")
    beam_width: int = Field(5, gt=0, description="CTC beam search width")
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)


class ClassifierModelConfig(BaseModel):
    """Config for the vehicle attribute classifier (color, make/model)."""

    name: str
    backend: InferenceBackend = InferenceBackend.onnx
    artifact_path: str = Field(..., description="Path to model artifact resolved according to the stack path_base")
    artifact_manifest_path: str | None = Field(None, description="Optional path to the promoted artifact manifest")
    label_metadata_path: str | None = Field(
        None,
        description="Optional sidecar metadata for classifier exports that emit logits instead of fully expanded attribute outputs",
    )
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
    path_base: ArtifactPathBase = Field(
        default=ArtifactPathBase.repo_root,
        description="How relative artifact paths should be resolved.",
    )
    vehicle_detector: DetectorModelConfig
    plate_detector: DetectorModelConfig
    ocr: OcrModelConfig
    classifier: Optional[ClassifierModelConfig] = Field(
        None, description="Classifier is optional; disable for inference-only deployments"
    )
    _config_dir: Path | None = PrivateAttr(default=None)

    def set_config_path(self, path: str | Path) -> None:
        self._config_dir = Path(path).resolve().parent

    def resolve_artifact_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        if self.path_base == ArtifactPathBase.config_dir and self._config_dir is not None:
            return (self._config_dir / path).resolve()
        return (Path.cwd() / path).resolve()
