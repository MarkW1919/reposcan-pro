"""Helpers for promoted model artifact manifests, validation, and packaging."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from shutil import copy2

import yaml
from pydantic import BaseModel, Field, ValidationError

from reposcan_contracts.config.loader import load_model_config
from reposcan_contracts.config.model import (
    ArtifactPathBase,
    ClassifierModelConfig,
    DetectorModelConfig,
    InferenceBackend,
    ModelStackConfig,
    OcrModelConfig,
)
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


class PromotedBundlePackageReport(BaseModel):
    bundle_name: str
    output_dir: str
    config_path: str
    ready: bool
    validation: PromotedBundleValidationReport


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
    resolved_artifact_path: str | Path | None = None,
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
    artifact_path = Path(resolved_artifact_path or model_config.artifact_path)
    return ModelArtifactManifest(
        stage=stage,  # type: ignore[arg-type]
        model_name=model_config.name,
        backend=model_config.backend,
        artifact_path=model_config.artifact_path,
        artifact_sha256=sha256_file(artifact_path),
        exported_at_utc=exported_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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


def _require_packagable_onnx_stack(model_stack: ModelStackConfig) -> None:
    runtime_report = validate_model_stack(model_stack)
    if not runtime_report.ready:
        raise ValueError("Source model stack is not runtime-ready and cannot be packaged as a promoted ONNX bundle.")
    non_onnx = [stage for stage, model in _stage_entries(model_stack) if model.backend != InferenceBackend.onnx]
    if non_onnx:
        raise ValueError(f"Promoted ONNX packaging currently supports ONNX-only stacks. Non-ONNX stages: {', '.join(non_onnx)}")


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
            manifest = load_model_artifact_manifest(model_stack.resolve_artifact_path(manifest_path))
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

        artifact_file = model_stack.resolve_artifact_path(model_config.artifact_path)
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


def package_promoted_onnx_bundle(
    model_stack: ModelStackConfig,
    *,
    output_dir: str | Path,
    bundle_name: str | None = None,
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
) -> PromotedBundlePackageReport:
    _require_packagable_onnx_stack(model_stack)

    bundle_root = Path(output_dir)
    artifacts_dir = bundle_root / "artifacts"
    manifests_dir = bundle_root / "manifests"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    bundle_stack_name = bundle_name or f"{model_stack.stack_name}-promoted"
    config_data = model_stack.model_dump(mode="json", exclude_none=True)
    config_data["stack_name"] = bundle_stack_name
    config_data["description"] = (
        f"Packaged promoted ONNX bundle derived from {model_stack.stack_name}"
    )
    config_data["path_base"] = ArtifactPathBase.config_dir.value

    copied_artifacts: dict[str, Path] = {}
    for stage, stage_config in _stage_entries(model_stack):
        source_artifact = model_stack.resolve_artifact_path(stage_config.artifact_path)
        target_artifact = artifacts_dir / source_artifact.name
        copy2(source_artifact, target_artifact)
        copied_artifacts[stage] = target_artifact
        config_data[stage]["artifact_path"] = Path("artifacts", target_artifact.name).as_posix()
        config_data[stage]["artifact_manifest_path"] = Path("manifests", f"{stage}.manifest.json").as_posix()

    config_path = bundle_root / "promoted-onnx.yaml"
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    bundled_stack = load_model_config(config_path)
    for stage, stage_config in _stage_entries(bundled_stack):
        manifest = build_model_artifact_manifest(
            stage=stage,
            model_config=stage_config,
            resolved_artifact_path=copied_artifacts[stage],
            exported_at_utc=exported_at_utc,
            source_run_id=source_run_id,
            source_checkpoint_ref=source_checkpoint_ref,
            dataset_manifests=dataset_manifests,
            export_tool=export_tool,
            export_tool_version=export_tool_version,
            opset_version=opset_version,
            precision=precision,
            target_runtime=target_runtime,
            notes=notes,
        )
        manifest_path = bundled_stack.resolve_artifact_path(stage_config.artifact_manifest_path or "")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    validation = validate_promoted_model_stack(bundled_stack)
    return PromotedBundlePackageReport(
        bundle_name=bundle_stack_name,
        output_dir=str(bundle_root),
        config_path=str(config_path),
        ready=validation.ready,
        validation=validation,
    )
