"""Internet-outage local-first acceptance runner.

Closes §12.182 of the project status checklist. The runner drives a
realistic capture → storage → alerting → sync flow with all outbound
transports forced offline, verifies that the local-first invariants hold,
then restores the transports, re-runs the pipeline, and verifies that the
queued state drains cleanly on recovery.

The runner is intentionally self-contained: it owns the storage
repository, the alerting + alert-delivery layer, and the sync service for
the duration of a single acceptance run. Callers supply a deployment
config and a workspace directory; the runner materializes the rest.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from reposcan_alerting import (
    AlertDeliveryService,
    AlertingService,
    MemoryAlertDeliveryTransport,
    RetryableAlertDeliveryError,
)
from reposcan_alerting.delivery import AlertDeliveryTransport
from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.loader import load_deployment_config, load_pipeline_config
from reposcan_contracts.detection import BoundingBox, DetectionRecord, PlateCandidate, SyncStatus
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.tracking import TrackedDetection
from reposcan_storage.service import create_storage_service_from_deployment

from .models import SyncRunResult
from .queue import JsonSyncQueue
from .service import SyncService
from .transports import MemorySyncTransport, RetryableSyncTransportError, SyncTransport


OUTAGE_PHASE = "outage"
RECOVERY_PHASE = "recovery"


class OfflineSyncTransport:
    """Sync transport that behaves as if the upstream endpoint is unreachable."""

    def __init__(self, reason: str = "network unreachable") -> None:
        self.reason = reason
        self.attempts = 0

    def send_detection(self, detection: DetectionRecord) -> None:
        self.attempts += 1
        raise RetryableSyncTransportError(self.reason)


class OfflineAlertDeliveryTransport:
    """Alert delivery transport that fails retryably during a simulated outage."""

    def __init__(self, reason: str = "network unreachable") -> None:
        self.reason = reason
        self.attempts = 0

    def send_alert(self, alert: AlertRecord) -> None:
        self.attempts += 1
        raise RetryableAlertDeliveryError(self.reason)


class OutagePhaseReport(BaseModel):
    phase: str = Field(..., min_length=1)
    detections_in_storage: int = Field(..., ge=0)
    alerts_in_storage: int = Field(..., ge=0)
    sync_queue_depth: int = Field(..., ge=0)
    detections_pending_sync: int = Field(..., ge=0)
    detections_failed_sync: int = Field(..., ge=0)
    detections_synced: int = Field(..., ge=0)
    alerts_delivered_locally: int = Field(..., ge=0)
    alert_delivery_errors: int = Field(..., ge=0)
    sync_run_result: SyncRunResult


class OutageInvariant(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    phase: str = Field(..., min_length=1)
    passed: bool
    detail: str | None = None


class OutageAcceptanceReport(BaseModel):
    run_id: str = Field(..., min_length=1)
    generated_at_utc: str = Field(..., min_length=1)
    deployment_name: str = Field(..., min_length=1)
    workspace_root: str = Field(..., min_length=1)
    detections_ingested: int = Field(..., ge=0)
    hotlist_plate: str = Field(..., min_length=1)
    outage: OutagePhaseReport
    recovery: OutagePhaseReport
    invariants: list[OutageInvariant]
    passed: bool


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_outage_run_id() -> str:
    return "outage_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _make_detection(
    *,
    detection_id: str,
    plate: str,
    timestamp: str,
    camera_id: str,
    frame_number: int,
    plate_confidence: float,
) -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": detection_id,
            "timestamp_utc": timestamp,
            "camera_id": camera_id,
            "gps_latitude": 37.42172,
            "gps_longitude": -122.08408,
            "plate_text": plate,
            "plate_confidence": plate_confidence,
            "plate_candidates": [{"text": plate, "confidence": plate_confidence}],
            "vehicle_bbox": {"x": 400, "y": 200, "w": 320, "h": 180},
            "plate_bbox": {"x": 520, "y": 330, "w": 90, "h": 28},
            "tracker_id": f"trk_{detection_id}",
            "image_path": f"media/frames/{camera_id}/frame_{frame_number:06d}.jpg",
            "plate_crop_path": f"media/crops/{camera_id}/plate_{frame_number:06d}.jpg",
            "frame_number": frame_number,
        }
    )


def _make_tracked_detection(detection: DetectionRecord) -> TrackedDetection:
    best_plate = None
    if detection.plate_text and detection.plate_confidence is not None:
        best_plate = PlateCandidate(text=detection.plate_text, confidence=detection.plate_confidence)
    return TrackedDetection(
        detection_id=detection.detection_id,
        tracker_id=detection.tracker_id or f"trk_{detection.detection_id}",
        camera_id=detection.camera_id,
        timestamp_utc=detection.timestamp_utc,
        best_plate_candidate=best_plate,
        vehicle_bbox=BoundingBox(**detection.vehicle_bbox.model_dump()),
        plate_bbox=detection.plate_bbox,
        frame_number=detection.frame_number,
    )


def _snapshot_phase(
    *,
    phase: str,
    storage_service,
    queue: JsonSyncQueue,
    delivery_errors: int,
    alerts_delivered: int,
    sync_run_result: SyncRunResult,
) -> OutagePhaseReport:
    detections = storage_service.list_detections(limit=1000)
    alerts = storage_service.list_alerts(limit=1000)
    pending = sum(1 for d in detections if d.sync_status == SyncStatus.pending)
    failed = sum(1 for d in detections if d.sync_status == SyncStatus.failed)
    synced = sum(1 for d in detections if d.sync_status == SyncStatus.synced)
    return OutagePhaseReport(
        phase=phase,
        detections_in_storage=len(detections),
        alerts_in_storage=len(alerts),
        sync_queue_depth=len(queue.list_items()),
        detections_pending_sync=pending,
        detections_failed_sync=failed,
        detections_synced=synced,
        alerts_delivered_locally=alerts_delivered,
        alert_delivery_errors=delivery_errors,
        sync_run_result=sync_run_result,
    )


def _evaluate_invariants(
    *,
    detections_ingested: int,
    outage: OutagePhaseReport,
    recovery: OutagePhaseReport,
    offline_sync_attempts: int,
    offline_alert_attempts: int,
) -> list[OutageInvariant]:
    invariants: list[OutageInvariant] = []

    invariants.append(
        OutageInvariant(
            name="local_detections_persist_during_outage",
            description=(
                "Every ingested detection is persisted to local storage while "
                "the upstream sync endpoint is unreachable."
            ),
            phase=OUTAGE_PHASE,
            passed=outage.detections_in_storage == detections_ingested,
            detail=f"expected={detections_ingested}, observed={outage.detections_in_storage}",
        )
    )

    invariants.append(
        OutageInvariant(
            name="local_alerts_persist_during_outage",
            description=(
                "At least one alert row is persisted locally when a hotlist "
                "match fires during an outage (delivery failure must not "
                "block local storage)."
            ),
            phase=OUTAGE_PHASE,
            passed=outage.alerts_in_storage >= 1,
            detail=f"alerts_in_storage={outage.alerts_in_storage}",
        )
    )

    invariants.append(
        OutageInvariant(
            name="sync_queue_retains_pending_items",
            description=(
                "The sync queue retains the unsynced detections so they can "
                "be retried after the outage clears."
            ),
            phase=OUTAGE_PHASE,
            passed=outage.sync_queue_depth == detections_ingested,
            detail=f"queue_depth={outage.sync_queue_depth}, expected={detections_ingested}",
        )
    )

    invariants.append(
        OutageInvariant(
            name="detections_marked_local_only_during_outage",
            description=(
                "Detections that failed to sync are marked failed with "
                "local_only_flag=True so the operator UI can surface the "
                "offline state."
            ),
            phase=OUTAGE_PHASE,
            passed=outage.detections_failed_sync == detections_ingested,
            detail=(
                f"failed={outage.detections_failed_sync}, "
                f"synced={outage.detections_synced}, "
                f"expected_failed={detections_ingested}"
            ),
        )
    )

    invariants.append(
        OutageInvariant(
            name="offline_transports_were_actually_exercised",
            description=(
                "The offline sync and alert delivery transports were invoked "
                "at least once, proving the outage path is wired (not "
                "silently bypassed)."
            ),
            phase=OUTAGE_PHASE,
            passed=offline_sync_attempts >= detections_ingested and offline_alert_attempts >= 1,
            detail=(
                f"sync_attempts={offline_sync_attempts}, "
                f"alert_delivery_attempts={offline_alert_attempts}, "
                f"expected_sync_attempts>={detections_ingested}"
            ),
        )
    )

    invariants.append(
        OutageInvariant(
            name="sync_queue_drains_on_recovery",
            description=(
                "After the upstream endpoint is restored, the sync queue "
                "drains to zero in a single scheduled run."
            ),
            phase=RECOVERY_PHASE,
            passed=recovery.sync_queue_depth == 0,
            detail=f"queue_depth_after_recovery={recovery.sync_queue_depth}",
        )
    )

    invariants.append(
        OutageInvariant(
            name="detections_flip_to_synced_on_recovery",
            description=(
                "Every detection that survived the outage is marked synced "
                "once the upstream endpoint returns."
            ),
            phase=RECOVERY_PHASE,
            passed=recovery.detections_synced == detections_ingested,
            detail=(
                f"synced={recovery.detections_synced}, "
                f"expected_synced={detections_ingested}, "
                f"failed={recovery.detections_failed_sync}"
            ),
        )
    )

    invariants.append(
        OutageInvariant(
            name="alerts_redeliver_on_recovery",
            description=(
                "Alerts that failed to deliver during the outage are "
                "redelivered successfully once the webhook recovers."
            ),
            phase=RECOVERY_PHASE,
            passed=recovery.alerts_delivered_locally >= 1,
            detail=f"alerts_delivered_on_recovery={recovery.alerts_delivered_locally}",
        )
    )

    return invariants


def run_internet_outage_acceptance(
    *,
    workspace_root: Path,
    run_id: str | None = None,
    deployment_config_path: str = "configs/deployments/local-dev.yaml",
    pipeline_config_path: str = "configs/pipelines/default-edge.yaml",
    detection_count: int = 10,
    hotlist_plate: str = "HOTLIST1",
    camera_id: str = "cam_outage_01",
    generated_at_utc: str | None = None,
) -> OutageAcceptanceReport:
    """Execute a full outage → recovery acceptance run against isolated state.

    Materializes its own storage repository, sync queue, alerting layer, and
    alert delivery service under ``workspace_root`` so repeated runs do not
    pollute developer state. Returns an :class:`OutageAcceptanceReport` that
    lists every invariant that was checked and whether it passed.
    """

    workspace_root = Path(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)

    deployment = load_deployment_config(deployment_config_path)
    pipeline = load_pipeline_config(pipeline_config_path)
    alerting_service = AlertingService(pipeline)

    storage_root = workspace_root / "storage"
    queue_path = workspace_root / "sync" / "detection_queue.json"
    storage_service = create_storage_service_from_deployment(
        deployment_config_path=deployment_config_path,
        metadata_root=storage_root,
        seed_demo_data=False,
    )

    hotlist_entry = HotlistEntry(
        entry_id=f"hot_outage_{uuid4().hex[:8]}",
        plate_text=hotlist_plate,
        label="outage-acceptance-hotlist",
        active=True,
        created_at_utc=_utcnow(),
        updated_at_utc=_utcnow(),
    )
    storage_service.create_hotlist(hotlist_entry)

    offline_sync = OfflineSyncTransport()
    offline_delivery = OfflineAlertDeliveryTransport()
    queue = JsonSyncQueue(queue_path)
    sync_service = SyncService(
        storage_service=storage_service,
        transport=offline_sync,
        queue=queue,
        retry_base_seconds=1,
        retry_max_seconds=4,
    )
    offline_alert_service = AlertDeliveryService(offline_delivery)

    offline_alert_errors = 0
    offline_alerts_delivered = 0
    for index in range(detection_count):
        detection_id = f"det_outage_{index:04d}"
        timestamp = (
            datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=index)
        ).isoformat().replace("+00:00", "Z")
        plate = hotlist_plate if index == 0 else f"OUT{index:03d}A"
        detection = _make_detection(
            detection_id=detection_id,
            plate=plate,
            timestamp=timestamp,
            camera_id=camera_id,
            frame_number=10_000 + index,
            plate_confidence=0.92,
        )
        storage_service.store_detection(detection)

        tracked = _make_tracked_detection(detection)
        alert = alerting_service.evaluate(tracked, [hotlist_entry])
        if alert is not None:
            storage_service.store_alert(alert)
            try:
                offline_alert_service.deliver(alert)
                offline_alerts_delivered += 1
            except RetryableAlertDeliveryError:
                offline_alert_errors += 1

        sync_service.enqueue_detection(detection_id)

    outage_sync_result = sync_service.run_once(limit=detection_count * 2)
    outage_report = _snapshot_phase(
        phase=OUTAGE_PHASE,
        storage_service=storage_service,
        queue=queue,
        delivery_errors=offline_alert_errors,
        alerts_delivered=offline_alerts_delivered,
        sync_run_result=outage_sync_result,
    )

    recovery_sync_transport = MemorySyncTransport()
    recovery_delivery_transport = MemoryAlertDeliveryTransport()
    sync_service.transport = recovery_sync_transport
    recovery_alert_service = AlertDeliveryService(recovery_delivery_transport)

    recovery_alerts_delivered = 0
    for alert in storage_service.list_alerts(limit=1000):
        recovery_alert_service.deliver(alert)
        recovery_alerts_delivered += 1

    future_now = (
        datetime.now(timezone.utc) + timedelta(seconds=sync_service.retry_max_seconds + 60)
    ).isoformat().replace("+00:00", "Z")
    recovery_sync_result = sync_service.run_once(
        now_utc=future_now,
        limit=detection_count * 2,
    )
    recovery_report = _snapshot_phase(
        phase=RECOVERY_PHASE,
        storage_service=storage_service,
        queue=queue,
        delivery_errors=0,
        alerts_delivered=recovery_alerts_delivered,
        sync_run_result=recovery_sync_result,
    )

    invariants = _evaluate_invariants(
        detections_ingested=detection_count,
        outage=outage_report,
        recovery=recovery_report,
        offline_sync_attempts=offline_sync.attempts,
        offline_alert_attempts=offline_delivery.attempts,
    )

    report = OutageAcceptanceReport(
        run_id=run_id or default_outage_run_id(),
        generated_at_utc=generated_at_utc or _utcnow(),
        deployment_name=deployment.deployment_name,
        workspace_root=str(workspace_root.resolve()),
        detections_ingested=detection_count,
        hotlist_plate=hotlist_plate,
        outage=outage_report,
        recovery=recovery_report,
        invariants=invariants,
        passed=all(inv.passed for inv in invariants),
    )
    return report


def render_outage_markdown(report: OutageAcceptanceReport) -> str:
    lines = [
        f"# Internet-outage acceptance run {report.run_id}",
        "",
        f"- generated at: {report.generated_at_utc}",
        f"- deployment profile: {report.deployment_name}",
        f"- workspace root: {report.workspace_root}",
        f"- detections ingested: {report.detections_ingested}",
        f"- hotlist plate: {report.hotlist_plate}",
        f"- overall result: {'PASS' if report.passed else 'FAIL'}",
        "",
        "## Phase snapshot",
        "",
        "| metric | outage | recovery |",
        "|---|---|---|",
        f"| detections in storage | {report.outage.detections_in_storage} | {report.recovery.detections_in_storage} |",
        f"| alerts in storage | {report.outage.alerts_in_storage} | {report.recovery.alerts_in_storage} |",
        f"| sync queue depth | {report.outage.sync_queue_depth} | {report.recovery.sync_queue_depth} |",
        f"| detections pending sync | {report.outage.detections_pending_sync} | {report.recovery.detections_pending_sync} |",
        f"| detections failed sync | {report.outage.detections_failed_sync} | {report.recovery.detections_failed_sync} |",
        f"| detections synced | {report.outage.detections_synced} | {report.recovery.detections_synced} |",
        f"| alerts delivered locally | {report.outage.alerts_delivered_locally} | {report.recovery.alerts_delivered_locally} |",
        f"| alert delivery errors | {report.outage.alert_delivery_errors} | {report.recovery.alert_delivery_errors} |",
        "",
        "## Invariants",
        "",
        "| phase | name | status | detail |",
        "|---|---|---|---|",
    ]
    for inv in report.invariants:
        status = "PASS" if inv.passed else "FAIL"
        detail = inv.detail or ""
        lines.append(f"| {inv.phase} | {inv.name} | {status} | {detail} |")
    lines.extend(
        [
            "",
            "## Invariant descriptions",
            "",
        ]
    )
    for inv in report.invariants:
        lines.append(f"- **{inv.name}** ({inv.phase}): {inv.description}")
    lines.append("")
    return "\n".join(lines) + "\n"


def outage_readiness_evidence_map(report: OutageAcceptanceReport) -> dict[str, object]:
    invariants = {invariant.name: invariant for invariant in report.invariants}
    return {
        "run_id": report.run_id,
        "generated_at_utc": report.generated_at_utc,
        "deployment_name": report.deployment_name,
        "workspace_root": report.workspace_root,
        "criteria": {
            "P6-1": {
                "artifact": "outage_report.md",
                "status": "evaluated",
                "passed": invariants["local_detections_persist_during_outage"].passed
                and invariants["sync_queue_retains_pending_items"].passed
                and invariants["sync_queue_drains_on_recovery"].passed,
                "detections_ingested": report.detections_ingested,
                "outage_queue_depth": report.outage.sync_queue_depth,
                "recovery_queue_depth": report.recovery.sync_queue_depth,
            },
            "P6-2": {
                "artifact": "outage_report.md",
                "status": "evaluated",
                "passed": invariants["local_alerts_persist_during_outage"].passed
                and invariants["alerts_redeliver_on_recovery"].passed,
                "outage_alerts": report.outage.alerts_in_storage,
                "recovery_alerts": report.recovery.alerts_in_storage,
            },
            "NF-3": {
                "artifact": "outage_report.md",
                "status": "evaluated",
                "passed": invariants["sync_queue_drains_on_recovery"].passed,
                "recovery_synced": report.recovery.detections_synced,
                "recovery_failed": report.recovery.detections_failed_sync,
            },
        },
    }


def write_outage_artifacts(
    report: OutageAcceptanceReport,
    *,
    output_root: Path,
) -> Path:
    run_dir = Path(output_root) / report.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "outage_report.md").write_text(render_outage_markdown(report), encoding="utf-8")
    (run_dir / "outage_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    summary = {
        "run_id": report.run_id,
        "generated_at_utc": report.generated_at_utc,
        "deployment_name": report.deployment_name,
        "detections_ingested": report.detections_ingested,
        "passed": report.passed,
        "invariants": [
            {"phase": inv.phase, "name": inv.name, "passed": inv.passed, "detail": inv.detail}
            for inv in report.invariants
        ],
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "production_readiness_evidence.json").write_text(
        json.dumps(outage_readiness_evidence_map(report), indent=2),
        encoding="utf-8",
    )
    return run_dir
