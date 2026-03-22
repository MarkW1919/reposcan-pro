"""RepoScan Pro inference service primitives."""

from .adapters import (
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from .profiling import InferenceLatencyProfile, InferenceProfiler, recommend_runtime_tuning
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
from .runtime_adapters import build_runtime_adapter_bundle
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
    "ModelAdapterBundle",
    "ModelStackValidationReport",
    "StageValidationReport",
    "StaticClassifierAdapter",
    "StaticOcrAdapter",
    "StaticPlateDetectorAdapter",
    "StaticVehicleDetectorAdapter",
    "ValidationIssue",
    "build_configured_adapter_bundle",
    "build_demo_adapter_bundle",
    "build_runtime_adapter_bundle",
    "recommend_runtime_tuning",
    "validate_model_stack",
]
