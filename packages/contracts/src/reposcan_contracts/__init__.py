"""reposcan_contracts - shared schemas and typed contracts for RepoScan Pro.

Importable by any service or app in the monorepo. Only contains schema
definitions and config loaders - no inference, IO, or business logic.
"""

from .alert import AlertRecord, AlertStatus
from .detection import BoundingBox, DetectionRecord, PlateCandidate, SyncStatus
from .frame import CameraProfile, FrameEnvelope, GpsSnapshot, PreparedFrame, PreprocessingMetadata, SourceType
from .health import DependencyHealth, HealthResponse, HealthState
from .hotlist import HotlistEntry, HotlistMatchResult
from .inference import AttributePredictions, InferenceCandidate, ModelVersions, PlateDetection, VehicleDetection
from .model_artifact import ModelArtifactManifest
from .popup import PopupActivityEvent, PopupEventType
from .review import ReviewAction, ReviewRecord
from .tracking import ConfidenceSummary, EvidenceRefs, TrackedDetection
from .types import PlateMatchType, UtcTimestamp

__version__ = "0.1.0"

__all__ = [
    "DetectionRecord",
    "BoundingBox",
    "PlateCandidate",
    "SyncStatus",
    "AlertRecord",
    "AlertStatus",
    "HotlistEntry",
    "HotlistMatchResult",
    "ReviewRecord",
    "ReviewAction",
    "HealthResponse",
    "DependencyHealth",
    "HealthState",
    "FrameEnvelope",
    "CameraProfile",
    "GpsSnapshot",
    "PreparedFrame",
    "PreprocessingMetadata",
    "SourceType",
    "InferenceCandidate",
    "VehicleDetection",
    "PlateDetection",
    "AttributePredictions",
    "ModelVersions",
    "ModelArtifactManifest",
    "TrackedDetection",
    "ConfidenceSummary",
    "EvidenceRefs",
    "PopupActivityEvent",
    "PopupEventType",
    "UtcTimestamp",
    "PlateMatchType",
]
