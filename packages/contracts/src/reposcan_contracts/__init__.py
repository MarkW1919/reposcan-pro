"""reposcan_contracts - shared schemas and typed contracts for RepoScan Pro.

Importable by any service or app in the monorepo. Only contains schema
definitions and config loaders - no inference, IO, or business logic.
"""

from .address_intel import (
    AddressIntelligenceReport,
    AddressMatchQuality,
    AreaContext,
    DwellingType,
)
from .alert import AlertRecord, AlertStatus
from .classifier_export import (
    ClassifierExportLabelRecord,
    ClassifierExportMetadata,
    build_classifier_export_metadata,
    parse_vehicle_make_model_year,
)
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
from .dataset_readiness import (
    DatasetReadinessIssue,
    DatasetReadinessLabelSummary,
    DatasetReadinessPolicy,
    DatasetReadinessReport,
    DatasetReadinessThresholds,
)
from .dispatch import DispatchAssignmentPriority, DispatchAssignmentRecord, DispatchAssignmentStatus
from .detection import BoundingBox, DetectionRecord, PlateCandidate, SyncStatus
from .field_eval import (
    FieldEvalAcceptanceThresholds,
    FieldEvalAsset,
    FieldEvalCoveragePolicy,
    FieldEvalDimensionResult,
    FieldEvalHoldoutManifest,
    FieldEvalQualificationIssue,
    FieldEvalQualificationReport,
    FieldEvalReport,
    FieldEvalScenario,
    FieldEvalSubsetSummary,
)
from .followup import FollowUpPriority, FollowUpRecord, FollowUpStatus
from .frame import CameraProfile, FrameEnvelope, GpsSnapshot, PreparedFrame, PreprocessingMetadata, SourceType
from .health import CameraHealthRecord, CameraHealthStatus, DependencyHealth, HealthResponse, HealthState
from .hotlist import HotlistEntry, HotlistMatchResult, QuickScanTarget, ScanArmMode
from .inference import AttributePredictions, InferenceCandidate, ModelVersions, PlateDetection, VehicleDetection
from .model_artifact import ModelArtifactManifest
from .occupant_intel import (
    OCCUPANT_BOUNDARY_CAVEAT,
    Occupant,
    OccupantIntelligenceReport,
    OccupantLookupStatus,
)
from .operator import OperatorCapabilities, OperatorPrincipal, OperatorSessionRecord
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
from .vehicle_catalog import (
    VehicleCatalogEntry,
    VehicleCatalogOverrideEntry,
    VehicleCatalogSeedEntry,
    VehicleRecognitionCatalog,
    VehicleRecognitionLabel,
)
from .logging import configure_logging, get_logger
from .types import HotlistMatchKind, PlateMatchType, UtcTimestamp

__version__ = "0.1.0"

__all__ = [
    "DetectionRecord",
    "BoundingBox",
    "PlateCandidate",
    "SyncStatus",
    "FieldEvalAcceptanceThresholds",
    "FieldEvalAsset",
    "FieldEvalCoveragePolicy",
    "FieldEvalDimensionResult",
    "FieldEvalHoldoutManifest",
    "FieldEvalQualificationIssue",
    "FieldEvalQualificationReport",
    "FieldEvalReport",
    "FieldEvalScenario",
    "FieldEvalSubsetSummary",
    "AddressIntelligenceReport",
    "AddressMatchQuality",
    "AreaContext",
    "DwellingType",
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
    "DatasetReadinessIssue",
    "DatasetReadinessLabelSummary",
    "DatasetReadinessPolicy",
    "DatasetReadinessReport",
    "DatasetReadinessThresholds",
    "DispatchAssignmentPriority",
    "DispatchAssignmentRecord",
    "DispatchAssignmentStatus",
    "FollowUpPriority",
    "FollowUpRecord",
    "FollowUpStatus",
    "HotlistEntry",
    "HotlistMatchResult",
    "QuickScanTarget",
    "ScanArmMode",
    "ReviewRecord",
    "ReviewAction",
    "HealthResponse",
    "CameraHealthRecord",
    "CameraHealthStatus",
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
    "OCCUPANT_BOUNDARY_CAVEAT",
    "Occupant",
    "OccupantIntelligenceReport",
    "OccupantLookupStatus",
    "OperatorCapabilities",
    "OperatorPrincipal",
    "OperatorSessionRecord",
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
    "HotlistMatchKind",
    "PlateMatchType",
    "configure_logging",
    "get_logger",
    "ClassifierExportLabelRecord",
    "ClassifierExportMetadata",
    "build_classifier_export_metadata",
    "parse_vehicle_make_model_year",
    "VehicleCatalogEntry",
    "VehicleCatalogOverrideEntry",
    "VehicleCatalogSeedEntry",
    "VehicleRecognitionCatalog",
    "VehicleRecognitionLabel",
]
