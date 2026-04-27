from __future__ import annotations

import json
from pathlib import Path

from reposcan_alerting import RetryableAlertDeliveryError
from reposcan_contracts.detection import DetectionRecord
from reposcan_sync import (
    OfflineAlertDeliveryTransport,
    OfflineSyncTransport,
    OUTAGE_PHASE,
    RECOVERY_PHASE,
    RetryableSyncTransportError,
    render_outage_markdown,
    run_internet_outage_acceptance,
    write_outage_artifacts,
    outage_readiness_evidence_map,
)


def _dummy_detection() -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": "det_outage_probe",
            "timestamp_utc": "2026-04-15T12:00:00Z",
            "camera_id": "cam_probe",
            "plate_text": "PROBE01",
            "plate_confidence": 0.9,
            "plate_candidates": [{"text": "PROBE01", "confidence": 0.9}],
            "vehicle_bbox": {"x": 1, "y": 2, "w": 30, "h": 40},
            "image_path": "media/frames/cam_probe/frame_000001.jpg",
            "frame_number": 1,
        }
    )


def test_offline_sync_transport_always_fails_retryably():
    transport = OfflineSyncTransport(reason="unit test outage")
    try:
        transport.send_detection(_dummy_detection())
    except RetryableSyncTransportError as exc:
        assert "unit test outage" in str(exc)
    else:
        raise AssertionError("OfflineSyncTransport did not raise a retryable error")
    assert transport.attempts == 1


def test_offline_alert_delivery_transport_always_fails_retryably():
    transport = OfflineAlertDeliveryTransport(reason="unit test alert outage")
    try:
        transport.send_alert(
            type(
                "StubAlert",
                (),
                {"alert_id": "x", "model_dump": lambda self, mode="json": {}},
            )()
        )
    except RetryableAlertDeliveryError as exc:
        assert "unit test alert outage" in str(exc)
    else:
        raise AssertionError("OfflineAlertDeliveryTransport did not raise a retryable error")
    assert transport.attempts == 1


def test_run_internet_outage_acceptance_passes_all_invariants(tmp_path: Path):
    report = run_internet_outage_acceptance(
        workspace_root=tmp_path / "workspace",
        run_id="outage_test_passes",
        detection_count=5,
        hotlist_plate="HOTLIST1",
    )

    assert report.run_id == "outage_test_passes"
    assert report.detections_ingested == 5
    assert report.deployment_name
    assert report.passed, "overall outage acceptance run should pass"

    assert report.outage.detections_in_storage == 5
    assert report.outage.alerts_in_storage == 1
    assert report.outage.sync_queue_depth == 5
    assert report.outage.detections_failed_sync == 5
    assert report.outage.detections_synced == 0
    assert report.outage.alert_delivery_errors == 1
    assert report.outage.alerts_delivered_locally == 0

    assert report.recovery.sync_queue_depth == 0
    assert report.recovery.detections_synced == 5
    assert report.recovery.detections_failed_sync == 0
    assert report.recovery.alerts_delivered_locally == 1

    phases = {inv.phase for inv in report.invariants}
    assert phases == {OUTAGE_PHASE, RECOVERY_PHASE}
    for inv in report.invariants:
        assert inv.passed, f"invariant {inv.name} failed: {inv.detail}"


def test_outage_artifacts_round_trip(tmp_path: Path):
    report = run_internet_outage_acceptance(
        workspace_root=tmp_path / "workspace",
        run_id="outage_test_artifacts",
        detection_count=3,
        hotlist_plate="HOTLIST1",
    )

    run_dir = write_outage_artifacts(report, output_root=tmp_path / "out")
    assert run_dir.name == "outage_test_artifacts"
    md_path = run_dir / "outage_report.md"
    json_path = run_dir / "outage_report.json"
    summary_path = run_dir / "run_manifest.json"
    evidence_path = run_dir / "production_readiness_evidence.json"
    assert md_path.exists()
    assert json_path.exists()
    assert summary_path.exists()
    assert evidence_path.exists()

    markdown = md_path.read_text(encoding="utf-8")
    assert "Internet-outage acceptance run outage_test_artifacts" in markdown
    assert "local_detections_persist_during_outage" in markdown
    assert "PASS" in markdown

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "outage_test_artifacts"
    assert payload["passed"] is True
    assert len(payload["invariants"]) >= 6

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["run_id"] == "outage_test_artifacts"
    assert summary["detections_ingested"] == 3
    assert summary["passed"] is True

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["run_id"] == "outage_test_artifacts"
    assert evidence["criteria"]["P6-1"]["artifact"] == "outage_report.md"
    assert evidence["criteria"]["P6-1"]["passed"] is True
    assert evidence["criteria"]["P6-2"]["passed"] is True
    assert evidence["criteria"]["NF-3"]["passed"] is True
    assert outage_readiness_evidence_map(report)["criteria"]["P6-1"]["detections_ingested"] == 3


def test_render_outage_markdown_contains_phase_snapshot(tmp_path: Path):
    report = run_internet_outage_acceptance(
        workspace_root=tmp_path / "workspace",
        run_id="outage_test_markdown",
        detection_count=2,
        hotlist_plate="HOTLIST1",
    )
    markdown = render_outage_markdown(report)
    assert "Phase snapshot" in markdown
    assert "outage" in markdown
    assert "recovery" in markdown
    assert "Invariant descriptions" in markdown
