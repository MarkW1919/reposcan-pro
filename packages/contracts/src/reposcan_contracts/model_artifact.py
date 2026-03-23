"""Model artifact promotion metadata shared across training, export, and runtime validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .config.model import InferenceBackend
from .types import UtcTimestamp


class ModelArtifactManifest(BaseModel):
    stage: Literal["vehicle_detector", "plate_detector", "ocr", "classifier"]
    model_name: str = Field(..., min_length=1)
    backend: InferenceBackend
    artifact_path: str = Field(..., min_length=1)
    artifact_sha256: str = Field(..., pattern=r"(?i)^[0-9a-f]{64}$")
    exported_at_utc: UtcTimestamp
    input_width: int = Field(..., gt=0)
    input_height: int = Field(..., gt=0)
    source_run_id: str | None = None
    source_checkpoint_ref: str | None = None
    dataset_manifests: list[str] = Field(default_factory=list)
    export_tool: str | None = None
    export_tool_version: str | None = None
    opset_version: int | None = Field(None, gt=0)
    precision: str | None = None
    target_runtime: str | None = None
    notes: str | None = None
