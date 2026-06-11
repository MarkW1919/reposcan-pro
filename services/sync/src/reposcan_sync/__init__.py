"""RepoScan Pro sync service primitives."""

from .models import SyncQueueItem, SyncRunResult
from .outage_runner import (
    OfflineAlertDeliveryTransport,
    OfflineSyncTransport,
    OutageAcceptanceReport,
    OutageInvariant,
    OutagePhaseReport,
    OUTAGE_PHASE,
    RECOVERY_PHASE,
    default_outage_run_id,
    outage_readiness_evidence_map,
    render_outage_markdown,
    run_internet_outage_acceptance,
    write_outage_artifacts,
)
from .queue import JsonSyncQueue
from .service import SyncService, create_development_sync_service
from .transports import (
    FlakySyncTransport,
    HttpSyncTransport,
    IdempotentSyncConflict,
    MemorySyncTransport,
    PermanentSyncTransportError,
    RetryableSyncTransportError,
    SyncTransport,
)

__all__ = [
    "FlakySyncTransport",
    "HttpSyncTransport",
    "IdempotentSyncConflict",
    "JsonSyncQueue",
    "MemorySyncTransport",
    "OfflineAlertDeliveryTransport",
    "OfflineSyncTransport",
    "OutageAcceptanceReport",
    "OutageInvariant",
    "OutagePhaseReport",
    "OUTAGE_PHASE",
    "PermanentSyncTransportError",
    "RECOVERY_PHASE",
    "RetryableSyncTransportError",
    "SyncQueueItem",
    "SyncRunResult",
    "SyncService",
    "SyncTransport",
    "create_development_sync_service",
    "default_outage_run_id",
    "outage_readiness_evidence_map",
    "render_outage_markdown",
    "run_internet_outage_acceptance",
    "write_outage_artifacts",
]
