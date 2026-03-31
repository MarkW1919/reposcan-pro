"""Model-stack validation helpers for runtime readiness checks."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from reposcan_contracts.config.model import (
    ClassifierModelConfig,
    DetectorModelConfig,
    InferenceBackend,
    ModelStackConfig,
    OcrModelConfig,
)

from .onnx_adapters import validate_onnx_artifact
from .runtime_adapters import (
    BuiltinClassifierArtifact,
    BuiltinOcrArtifact,
    BuiltinPlateDetectorArtifact,
    BuiltinVehicleDetectorArtifact,
)


class ValidationIssue(BaseModel):
    severity: str = Field(pattern="^(error|warning)$")
    stage: str
    message: str


class StageValidationReport(BaseModel):
    stage: str
    backend: str
    artifact_path: str
    ready: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class ModelStackValidationReport(BaseModel):
    stack_name: str
    ready: bool
    stages: list[StageValidationReport] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for stage in self.stages for issue in stage.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for stage in self.stages for issue in stage.issues if issue.severity == "warning")


def _artifact_exists(path: str | Path) -> Path:
    artifact_path = Path(path)
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact '{artifact_path}' does not exist")
    return artifact_path


def _validate_builtin(stage: str, artifact_path: Path) -> list[ValidationIssue]:
    validators = {
        "vehicle_detector": BuiltinVehicleDetectorArtifact,
        "plate_detector": BuiltinPlateDetectorArtifact,
        "ocr": BuiltinOcrArtifact,
        "classifier": BuiltinClassifierArtifact,
    }
    model = validators[stage]
    try:
        model.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        return [ValidationIssue(severity="error", stage=stage, message=str(exc))]
    return []


def _validate_exported_backend(stage: str, backend: InferenceBackend, artifact_path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    suffix = artifact_path.suffix.lower()
    if backend == InferenceBackend.onnx and suffix != ".onnx":
        issues.append(
            ValidationIssue(
                severity="warning",
                stage=stage,
                message=f"Expected an .onnx artifact for {stage}, found '{artifact_path.name}'.",
            )
        )
    elif backend == InferenceBackend.tensorrt and suffix not in {".engine", ".trt"}:
        issues.append(
            ValidationIssue(
                severity="warning",
                stage=stage,
                message=f"Expected a TensorRT engine artifact for {stage}, found '{artifact_path.name}'.",
            )
        )
    elif backend == InferenceBackend.pytorch and suffix not in {".pt", ".pth", ".ckpt"}:
        issues.append(
            ValidationIssue(
                severity="warning",
                stage=stage,
                message=f"Expected a PyTorch checkpoint for {stage}, found '{artifact_path.name}'.",
            )
        )
    elif backend == InferenceBackend.onnx:
        return []
    return issues


def _stage_report(
    model_stack: ModelStackConfig,
    stage: str,
    model_config: DetectorModelConfig | OcrModelConfig | ClassifierModelConfig,
) -> StageValidationReport:
    issues: list[ValidationIssue] = []
    try:
        artifact_path = _artifact_exists(model_stack.resolve_artifact_path(model_config.artifact_path))
    except FileNotFoundError as exc:
        issues.append(ValidationIssue(severity="error", stage=stage, message=str(exc)))
        return StageValidationReport(
            stage=stage,
            backend=model_config.backend.value,
            artifact_path=model_config.artifact_path,
            ready=False,
            issues=issues,
        )

    if model_config.backend == InferenceBackend.builtin:
        issues.extend(_validate_builtin(stage, artifact_path))
    elif model_config.backend == InferenceBackend.onnx:
        metadata_path = None
        if isinstance(model_config, ClassifierModelConfig) and model_config.label_metadata_path:
            metadata_path = model_stack.resolve_artifact_path(model_config.label_metadata_path)
        issues.extend(
            ValidationIssue(severity="error", stage=stage, message=message)
            for message in validate_onnx_artifact(
                stage,
                model_config,
                artifact_path=artifact_path,
                metadata_path=metadata_path,
            )
        )
    else:
        issues.extend(_validate_exported_backend(stage, model_config.backend, artifact_path))

    ready = not any(issue.severity == "error" for issue in issues)
    return StageValidationReport(
        stage=stage,
        backend=model_config.backend.value,
        artifact_path=model_config.artifact_path,
        ready=ready,
        issues=issues,
    )


def validate_model_stack(model_stack: ModelStackConfig) -> ModelStackValidationReport:
    stages = [
        _stage_report(model_stack, "vehicle_detector", model_stack.vehicle_detector),
        _stage_report(model_stack, "plate_detector", model_stack.plate_detector),
        _stage_report(model_stack, "ocr", model_stack.ocr),
    ]
    if model_stack.classifier is not None:
        stages.append(_stage_report(model_stack, "classifier", model_stack.classifier))

    return ModelStackValidationReport(
        stack_name=model_stack.stack_name,
        ready=all(stage.ready for stage in stages),
        stages=stages,
    )
