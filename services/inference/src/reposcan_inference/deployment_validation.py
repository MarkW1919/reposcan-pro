"""Deployment-target compatibility checks for promoted runtime bundles."""

from __future__ import annotations

from pydantic import BaseModel, Field

from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.config.model import ClassifierModelConfig, DetectorModelConfig, ModelStackConfig, OcrModelConfig

from .promotion import load_model_artifact_manifest, validate_promoted_model_stack

_StageConfig = DetectorModelConfig | OcrModelConfig | ClassifierModelConfig


class DeploymentValidationIssue(BaseModel):
    severity: str = Field(pattern="^(error|warning)$")
    scope: str
    message: str


class DeploymentCompatibilityReport(BaseModel):
    deployment_name: str
    stack_name: str
    runtime_ready: bool
    promotion_ready: bool
    ready: bool
    issues: list[DeploymentValidationIssue] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


def _stage_entries(model_stack: ModelStackConfig) -> list[tuple[str, _StageConfig]]:
    entries: list[tuple[str, _StageConfig]] = [
        ("vehicle_detector", model_stack.vehicle_detector),
        ("plate_detector", model_stack.plate_detector),
        ("ocr", model_stack.ocr),
    ]
    if model_stack.classifier is not None:
        entries.append(("classifier", model_stack.classifier))
    return entries


def validate_deployment_runtime_bundle(
    model_stack: ModelStackConfig,
    deployment: DeploymentConfig,
) -> DeploymentCompatibilityReport:
    promotion_report = validate_promoted_model_stack(model_stack)
    issues: list[DeploymentValidationIssue] = []
    runtime_requirements = deployment.runtime

    if runtime_requirements.required_path_base and model_stack.path_base != runtime_requirements.required_path_base:
        issues.append(
            DeploymentValidationIssue(
                severity="error",
                scope="bundle",
                message=(
                    f"Deployment requires path_base '{runtime_requirements.required_path_base.value}', "
                    f"found '{model_stack.path_base.value}'."
                ),
            )
        )

    if runtime_requirements.required_backend:
        mismatched_stages = [
            stage
            for stage, model_config in _stage_entries(model_stack)
            if model_config.backend != runtime_requirements.required_backend
        ]
        if mismatched_stages:
            issues.append(
                DeploymentValidationIssue(
                    severity="error",
                    scope="bundle",
                    message=(
                        f"Deployment requires backend '{runtime_requirements.required_backend.value}' for all stages; "
                        f"mismatched stages: {', '.join(mismatched_stages)}."
                    ),
                )
            )

    if promotion_report.ready:
        for stage, model_config in _stage_entries(model_stack):
            if not model_config.artifact_manifest_path:
                continue
            manifest = load_model_artifact_manifest(model_stack.resolve_artifact_path(model_config.artifact_manifest_path))

            if runtime_requirements.target_runtime and manifest.target_runtime != runtime_requirements.target_runtime:
                issues.append(
                    DeploymentValidationIssue(
                        severity="error",
                        scope=stage,
                        message=(
                            f"Deployment requires target_runtime '{runtime_requirements.target_runtime}', "
                            f"found '{manifest.target_runtime}'."
                        ),
                    )
                )
            if runtime_requirements.required_cuda_version and manifest.cuda_version != runtime_requirements.required_cuda_version:
                issues.append(
                    DeploymentValidationIssue(
                        severity="error",
                        scope=stage,
                        message=(
                            f"Deployment requires cuda_version '{runtime_requirements.required_cuda_version}', "
                            f"found '{manifest.cuda_version}'."
                        ),
                    )
                )
            if runtime_requirements.required_tensorrt_version and manifest.tensorrt_version != runtime_requirements.required_tensorrt_version:
                issues.append(
                    DeploymentValidationIssue(
                        severity="error",
                        scope=stage,
                        message=(
                            f"Deployment requires tensorrt_version '{runtime_requirements.required_tensorrt_version}', "
                            f"found '{manifest.tensorrt_version}'."
                        ),
                    )
                )
            if (
                runtime_requirements.required_compute_capability
                and manifest.device_compute_capability != runtime_requirements.required_compute_capability
            ):
                issues.append(
                    DeploymentValidationIssue(
                        severity="error",
                        scope=stage,
                        message=(
                            "Deployment requires device_compute_capability "
                            f"'{runtime_requirements.required_compute_capability}', "
                            f"found '{manifest.device_compute_capability}'."
                        ),
                    )
                )

    ready = promotion_report.ready and not any(issue.severity == "error" for issue in issues)
    return DeploymentCompatibilityReport(
        deployment_name=deployment.deployment_name,
        stack_name=model_stack.stack_name,
        runtime_ready=promotion_report.runtime_ready,
        promotion_ready=promotion_report.ready,
        ready=ready,
        issues=issues,
    )
