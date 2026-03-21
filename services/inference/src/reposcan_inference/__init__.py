"""RepoScan Pro inference service primitives."""

from .adapters import (
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from .profiling import InferenceLatencyProfile, InferenceProfiler, recommend_runtime_tuning
from .runtime import FrameEnvelopeQueue, HeadlessFileSequenceRunner, HeadlessRunSummary, build_demo_adapter_bundle
from .service import InferenceService
from .workflow import FrameToCandidateWorkflow

__all__ = [
    "FrameToCandidateWorkflow",
    "FrameEnvelopeQueue",
    "HeadlessFileSequenceRunner",
    "HeadlessRunSummary",
    "InferenceLatencyProfile",
    "InferenceProfiler",
    "InferenceService",
    "ModelAdapterBundle",
    "StaticClassifierAdapter",
    "StaticOcrAdapter",
    "StaticPlateDetectorAdapter",
    "StaticVehicleDetectorAdapter",
    "build_demo_adapter_bundle",
    "recommend_runtime_tuning",
]
