"""reposcan_contracts - shared schemas and typed contracts for RepoScan Pro.

Importable by any service or app in the monorepo. Only contains schema
definitions and config loaders - no inference, IO, or business logic.
"""

from .alert import AlertRecord, AlertStatus
from .benchmark import BenchmarkFrameExpectation, PromotedModelBenchmarkManifest
from .dataset import (
    AnnotationReview,
    AnnotationTask,
    DatasetAssetRecord,
    DatasetFormat,
    DatasetLicenseTier,
    DatasetProvenance,
    DatasetReviewStatus,
    DatasetSourceKind,
    DatasetSplit,
    DatasetSplitAssignment,
    DatasetSplitManifest,
    DatasetSplitSource,
    DatasetTask,
    DistanceBand,
    LightingCondition,
    TrainingDatasetManifest,
)
from .detection import BoundingBox, DetectionRecord, PlateCandidate, SyncStatus
from .frame import CameraProfile, FrameEnvelope, GpsSnapshot, PreparedFrame, PreprocessingMetadata, SourceType
from .health import DependencyHealth, HealthResponse, HealthState
from .hotlist import HotlistEntry, HotlistMatchResult
from .inference import AttributePredictions, InferenceCandidate, ModelVersions, PlateDetection, VehicleDetection
from .model_artifact import ModelArtifactManifest
from .popup import PopupActivityEvent, PopupEventType
from .review import ReviewAction, ReviewRecord
from .training import (
    AugmentationPolicy,
    DatasetAdapter,
    TrainingFramework,
    TrainingProfileConfig,
    TrainingRunManifest,
)
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
    "BenchmarkFrameExpectation",
    "PromotedModelBenchmarkManifest",
    "TrainingDatasetManifest",
    "DatasetTask",
    "DatasetFormat",
    "DatasetSourceKind",
    "DatasetLicenseTier",
    "DatasetReviewStatus",
    "DatasetSplit",
    "AnnotationTask",
    "LightingCondition",
    "DistanceBand",
    "DatasetProvenance",
    "AnnotationReview",
    "DatasetAssetRecord",
    "DatasetSplitSource",
    "DatasetSplitAssignment",
    "DatasetSplitManifest",
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
    "TrainingFramework",
    "DatasetAdapter",
    "AugmentationPolicy",
    "TrainingProfileConfig",
    "TrainingRunManifest",
    "UtcTimestamp",
    "PlateMatchType",
]
