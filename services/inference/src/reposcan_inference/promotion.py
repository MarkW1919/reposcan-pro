"""Helpers for promoted model artifact manifests and bundle validation."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from reposcan_contracts.config.model import ClassifierModelConfig, DetectorModelConfig, ModelStackConfig, OcrModelConfig
from reposcan_contracts.model_artifact import ModelArtifactManifest

from .validation import validate_model_stack

_StageConfig = DetectorModelConfig | OcrModelConfig | ClassifierModelConfig


class PromotionIssue(BaseModel):
    severity: str = Field(pattern="^(error|warning)$")
    stage: str
    message: str


class PromotedStageValidationReport(BaseModel):
    stage: str
    artifact_path: str
    artifact_manifest_path: str | None = None
    ready: bool
    issues: list[PromotionIssue] = Field(default_factory=list)


class PromotedBundleValidationReport(BaseModel):
    stack_name: str
    runtime_ready: bool
    ready: bool
    stages: list[PromotedStageValidationReport] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for stage in self.stages for issue in stage.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for stage in self.stages for issue in stage.issues if issue.severity == "warning")


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model_artifact_manifest(path: str | Path) -> ModelArtifactManifest:
    artifact_path = Path(path)
    data = artifact_path.read_text(encoding="utf-8")
    return ModelArtifactManifest.model_validate_json(data)


def build_model_artifact_manifest(
    *,
    stage: str,
    model_config: _StageConfig,
    exported_at_utc: str | None = None,
    source_run_id: str | None = None,
    source_checkpoint_ref: str | None = None,
    dataset_manifests: list[str] | None = None,
    export_tool: str | None = None,
    export_tool_version: str | None = None,
    opset_version: int | None = None,
    precision: str | None = None,
    target_runtime: str | None = None,
    notes: str | None = None,
) -> ModelArtifactManifest:
    return ModelArtifactManifest(
        stage=stage,  # type: ignore[arg-type]
        model_name=model_config.name,
        backend=model_config.backend,
        artifact_path=model_config.artifact_path,
        artifact_sha256=sha256_file(model_config.artifact_path),
        exported_at_utc=exported_at_utc
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        input_width=model_config.input_width,
        input_height=model_config.input_height,
        source_run_id=source_run_id,
        source_checkpoint_ref=source_checkpoint_ref,
        dataset_manifests=dataset_manifests or [],
        export_tool=export_tool,
        export_tool_version=export_tool_version,
        opset_version=opset_version,
        precision=precision,
        target_runtime=target_runtime,
        notes=notes,
    )


def _stage_entries(model_stack: ModelStackConfig) -> list[tuple[str, _StageConfig]]:
    entries: list[tuple[str, _StageConfig]] = [
        ("vehicle_detector", model_stack.vehicle_detector),
        ("plate_detector", model_stack.plate_detector),
        ("ocr", model_stack.ocr),
    ]
    if model_stack.classifier is not None:
        entries.append(("classifier", model_stack.classifier))
    return entries


def validate_promoted_model_stack(model_stack: ModelStackConfig) -> PromotedBundleValidationReport:
    runtime_report = validate_model_stack(model_stack)
    stage_reports: list[PromotedStageValidationReport] = []

    for stage, model_config in _stage_entries(model_stack):
        issues: list[PromotionIssue] = []
        manifest_path = model_config.artifact_manifest_path
        if not manifest_path:
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message="artifact_manifest_path is required for promoted bundle validation.",
                )
            )
            stage_reports.append(
                PromotedStageValidationReport(
                    stage=stage,
                    artifact_path=model_config.artifact_path,
                    ready=False,
                    issues=issues,
                )
            )
            continue

        try:
            manifest = load_model_artifact_manifest(manifest_path)
        except (OSError, ValidationError, ValueError) as exc:
            issues.append(PromotionIssue(severity="error", stage=stage, message=str(exc)))
            stage_reports.append(
                PromotedStageValidationReport(
                    stage=stage,
                    artifact_path=model_config.artifact_path,
                    artifact_manifest_path=manifest_path,
                    ready=False,
                    issues=issues,
                )
            )
            continue

        if manifest.stage != stage:
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message=f"Manifest stage '{manifest.stage}' does not match config stage '{stage}'.",
                )
            )
        if manifest.model_name != model_config.name:
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message=f"Manifest model_name '{manifest.model_name}' does not match config name '{model_config.name}'.",
                )
            )
        if manifest.backend != model_config.backend:
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message=f"Manifest backend '{manifest.backend.value}' does not match config backend '{model_config.backend.value}'.",
                )
            )
        if manifest.artifact_path != model_config.artifact_path:
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message=f"Manifest artifact_path '{manifest.artifact_path}' does not match config artifact_path '{model_config.artifact_path}'.",
                )
            )
        if manifest.input_width != model_config.input_width or manifest.input_height != model_config.input_height:
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message="Manifest input dimensions do not match the model config.",
                )
            )

        artifact_file = Path(model_config.artifact_path)
        if not artifact_file.exists():
            issues.append(
                PromotionIssue(
                    severity="error",
                    stage=stage,
                    message=f"Artifact '{artifact_file}' does not exist.",
                )
            )
        else:
            actual_sha256 = sha256_file(artifact_file)
            if actual_sha256 != manifest.artifact_sha256:
                issues.append(
                    PromotionIssue(
                        severity="error",
                        stage=stage,
                        message="Artifact sha256 does not match the manifest.",
                    )
                )

        stage_reports.append(
            PromotedStageValidationReport(
                stage=stage,
                artifact_path=model_config.artifact_path,
                artifact_manifest_path=manifest_path,
                ready=not any(issue.severity == "error" for issue in issues),
                issues=issues,
            )
        )

    ready = runtime_report.ready and all(stage.ready for stage in stage_reports)
    return PromotedBundleValidationReport(
        stack_name=model_stack.stack_name,
        runtime_ready=runtime_report.ready,
        ready=ready,
        stages=stage_reports,
    )
