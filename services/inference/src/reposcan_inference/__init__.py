"""RepoScan Pro inference service primitives."""

from .adapters import (
    ModelAdapterBundle,
    StaticClassifierAdapter,
    StaticOcrAdapter,
    StaticPlateDetectorAdapter,
    StaticVehicleDetectorAdapter,
)
from .service import InferenceService
from .workflow import FrameToCandidateWorkflow

__all__ = [
    "FrameToCandidateWorkflow",
    "InferenceService",
    "ModelAdapterBundle",
    "StaticClassifierAdapter",
    "StaticOcrAdapter",
    "StaticPlateDetectorAdapter",
    "StaticVehicleDetectorAdapter",
]
