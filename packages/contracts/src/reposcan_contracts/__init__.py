"""reposcan_contracts - shared schemas and typed contracts for RepoScan Pro.

Importable by any service or app in the monorepo. Only contains schema
definitions and config loaders - no inference, IO, or business logic.
"""

from .alert import AlertRecord, AlertStatus
from .benchmark import (
    BenchmarkFrameExpectation,
    BenchmarkSubsetMetrics,
    BenchmarkValidationSummary,
    PromotedModelBenchmarkManifest,
    PromotedModelBenchmarkReport,
)
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
from .field_eval import (
    FieldEvalCoveragePolicy,
    FieldEvalQualificationIssue,
    FieldEvalQualificationReport,
    FieldEvalSubsetSummary,
)
from .frame import CameraProfile, FrameEnvelope, GpsSnapshot, PreparedFrame, PreprocessingMetadata, SourceType
from .health import DependencyHealth, HealthResponse, HealthState
from .hotlist import HotlistEntry, HotlistMatchResult
from .inference import AttributePredictions, InferenceCandidate, ModelVersions, PlateDetection, VehicleDetection
from .model_artifact import ModelArtifactManifest
from .popup import PopupActivityEvent, PopupEventType
from .release import (
    ModelReleaseChannel,
    ModelReleaseRecord,
    ReleaseBenchmarkSummary,
    ReleaseChannelAction,
    ReleaseChannelEvent,
    ReleaseValidationSummary,
)
from .review import ReviewAction, ReviewRecord
from .training import (
    AugmentationPolicy,
    DatasetAdapter,
    TrainingFramework,
    TrainingProfileConfig,
    TrainingRunManifest,
)
from .tracking import ConfidenceSummary, EvidenceRefs, TrackedDetection
from .tracking_benchmark import (
    TrackingAlgorithmBenchmark,
    TrackingScenarioMetrics,
    TrackingStrategyBenchmarkReport,
)
from .types import PlateMatchType, UtcTimestamp

__version__ = "0.1.0"

__all__ = [
    "DetectionRecord",
    "BoundingBox",
    "PlateCandidate",
    "SyncStatus",
    "FieldEvalCoveragePolicy",
    "FieldEvalQualificationIssue",
    "FieldEvalQualificationReport",
    "FieldEvalSubsetSummary",
    "AlertRecord",
    "AlertStatus",
    "BenchmarkFrameExpectation",
    "BenchmarkSubsetMetrics",
    "BenchmarkValidationSummary",
    "PromotedModelBenchmarkManifest",
    "PromotedModelBenchmarkReport",
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
    "TrackingAlgorithmBenchmark",
    "TrackingScenarioMetrics",
    "TrackingStrategyBenchmarkReport",
    "PopupActivityEvent",
    "PopupEventType",
    "ReleaseBenchmarkSummary",
    "ReleaseChannelAction",
    "ReleaseChannelEvent",
    "ReleaseValidationSummary",
    "ModelReleaseRecord",
    "ModelReleaseChannel",
    "TrainingFramework",
    "DatasetAdapter",
    "AugmentationPolicy",
    "TrainingProfileConfig",
    "TrainingRunManifest",
    "UtcTimestamp",
    "PlateMatchType",
]
