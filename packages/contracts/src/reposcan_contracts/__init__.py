"""reposcan_contracts — shared schemas and typed contracts for RepoScan Pro.

Importable by any service or app in the monorepo.  Only contains schema
definitions and config loaders — no inference, IO, or business logic.
"""

from .alert import AlertRecord, AlertStatus
from .detection import BoundingBox, DetectionRecord, PlateCandidate, SyncStatus
from .frame import CameraProfile, FrameEnvelope, GpsSnapshot, SourceType
from .health import DependencyHealth, HealthResponse, HealthState
from .hotlist import HotlistEntry, HotlistMatchResult
from .inference import AttributePredictions, InferenceCandidate, ModelVersions, PlateDetection, VehicleDetection
from .review import ReviewAction, ReviewRecord
from .tracking import ConfidenceSummary, EvidenceRefs, TrackedDetection

__version__ = "0.1.0"

__all__ = [
    # detection
    "DetectionRecord",
    "BoundingBox",
    "PlateCandidate",
    "SyncStatus",
    # alert
    "AlertRecord",
    "AlertStatus",
    # hotlist
    "HotlistEntry",
    "HotlistMatchResult",
    # review
    "ReviewRecord",
    "ReviewAction",
    # health
    "HealthResponse",
    "DependencyHealth",
    "HealthState",
    # frame (inter-service)
    "FrameEnvelope",
    "CameraProfile",
    "GpsSnapshot",
    "SourceType",
    # inference (inter-service)
    "InferenceCandidate",
    "VehicleDetection",
    "PlateDetection",
    "AttributePredictions",
    "ModelVersions",
    # tracking (inter-service)
    "TrackedDetection",
    "ConfidenceSummary",
    "EvidenceRefs",
]
