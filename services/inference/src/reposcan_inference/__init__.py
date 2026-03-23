"""RepoScan Pro inference service primitives."""

from .adapters import (
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from .adapter_factory import build_runtime_adapter_bundle
from .deployment_validation import (
    DeploymentCompatibilityReport,
    DeploymentValidationIssue,
    validate_deployment_runtime_bundle,
)
from .onnx_adapters import build_onnx_adapter_bundle, validate_onnx_artifact
from .profiling import InferenceLatencyProfile, InferenceProfiler, recommend_runtime_tuning
from .promotion import (
    PromotedBundlePackageReport,
    PromotedBundleValidationReport,
    PromotedStageValidationReport,
    PromotionIssue,
    build_model_artifact_manifest,
    load_model_artifact_manifest,
    package_promoted_onnx_bundle,
    sha256_file,
    validate_promoted_model_stack,
)
from .runtime import (
    DemoRunInProgressError,
    DemoRunRequest,
    DemoRunStatus,
    FrameEnvelopeQueue,
    HeadlessDemoRunManager,
    HeadlessFileSequenceRunner,
    HeadlessRunSummary,
    build_configured_adapter_bundle,
    build_demo_adapter_bundle,
)
from .runtime_adapters import build_builtin_runtime_adapter_bundle
from .service import InferenceService
from .validation import ModelStackValidationReport, StageValidationReport, ValidationIssue, validate_model_stack
from .workflow import FrameToCandidateWorkflow

__all__ = [
    "FrameToCandidateWorkflow",
    "DemoRunInProgressError",
    "DemoRunRequest",
    "DemoRunStatus",
    "FrameEnvelopeQueue",
    "HeadlessDemoRunManager",
    "HeadlessFileSequenceRunner",
    "HeadlessRunSummary",
    "InferenceLatencyProfile",
    "InferenceProfiler",
    "InferenceService",
    "DeploymentCompatibilityReport",
    "DeploymentValidationIssue",
    "ModelAdapterBundle",
    "ModelStackValidationReport",
    "PromotedBundlePackageReport",
    "PromotedBundleValidationReport",
    "PromotedStageValidationReport",
    "PromotionIssue",
    "StageValidationReport",
    "StaticClassifierAdapter",
    "StaticOcrAdapter",
    "StaticPlateDetectorAdapter",
    "StaticVehicleDetectorAdapter",
    "ValidationIssue",
    "build_builtin_runtime_adapter_bundle",
    "build_model_artifact_manifest",
    "build_onnx_adapter_bundle",
    "build_configured_adapter_bundle",
    "build_demo_adapter_bundle",
    "build_runtime_adapter_bundle",
    "load_model_artifact_manifest",
    "package_promoted_onnx_bundle",
    "recommend_runtime_tuning",
    "sha256_file",
    "validate_deployment_runtime_bundle",
    "validate_onnx_artifact",
    "validate_model_stack",
    "validate_promoted_model_stack",
]
