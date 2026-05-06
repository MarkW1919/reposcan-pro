from __future__ import annotations

import pytest
from pydantic import ValidationError

from reposcan_contracts.dispatch import DispatchAssignmentRecord, DispatchAssignmentStatus
from reposcan_contracts.followup import FollowUpPriority, FollowUpRecord, FollowUpStatus
from reposcan_contracts.operator import (
    OperatorCapabilities,
    OperatorPrincipal,
    OperatorSessionRecord,
    ScanProcessingMode,
    ScanSessionState,
)


class TestFollowUpRecord:
    def _valid(self, **overrides) -> dict:
        base = {
            "follow_up_id": "fu_001",
            "detection_id": "det_001",
            "plate_text": " 8abc123 ",
            "priority": "priority",
            "status": "open",
            "created_at_utc": "2026-03-26T04:15:00Z",
            "updated_at_utc": "2026-03-26T04:16:00Z",
        }
        base.update(overrides)
        return base

    def test_plate_text_normalizes_to_uppercase(self):
        record = FollowUpRecord.model_validate(self._valid())
        assert record.plate_text == "8ABC123"

    def test_status_and_priority_roundtrip(self):
        for status in FollowUpStatus:
            for priority in FollowUpPriority:
                record = FollowUpRecord.model_validate(self._valid(status=status, priority=priority))
                assert record.status == status
                assert record.priority == priority


class TestDispatchAssignmentRecord:
    def _valid(self, **overrides) -> dict:
        base = {
            "assignment_id": "asg_001",
            "detection_id": "det_001",
            "plate_text": "8abc123",
            "status": "queued",
            "created_at_utc": "2026-03-26T04:15:00Z",
            "updated_at_utc": "2026-03-26T04:16:00Z",
        }
        base.update(overrides)
        return base

    def test_assignment_status_roundtrip(self):
        for status in DispatchAssignmentStatus:
            record = DispatchAssignmentRecord.model_validate(self._valid(status=status))
            assert record.status == status

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            DispatchAssignmentRecord.model_validate(self._valid(updated_at_utc="2026-03-26 04:16:00"))


class TestOperatorPresenceContracts:
    def test_operator_principal_roundtrips_capabilities(self):
        principal = OperatorPrincipal.model_validate(
            {
                "principal_id": "operator_demo",
                "display_name": "Operator Demo",
                "authenticated": True,
                "roles": ["viewer", "operator"],
                "capabilities": {
                    "can_submit_reviews": True,
                    "can_update_alerts": True,
                    "can_manage_hotlists": False,
                    "can_manage_follow_ups": True,
                    "can_manage_dispatch": True,
                    "can_start_demo_runs": True,
                    "can_view_audit": False,
                },
            }
        )

        assert principal.capabilities == OperatorCapabilities.model_validate(
            {
                "can_submit_reviews": True,
                "can_update_alerts": True,
                "can_manage_hotlists": False,
                "can_manage_follow_ups": True,
                "can_manage_dispatch": True,
                "can_start_demo_runs": True,
                "can_view_audit": False,
            }
        )

    def test_operator_session_requires_utc_timestamp(self):
        with pytest.raises(ValidationError):
            OperatorSessionRecord.model_validate(
                {
                    "session_id": "session_001",
                    "principal_id": "operator_demo",
                    "workspace": "dashboard",
                    "last_seen_at_utc": "2026-03-26 04:16:00",
                }
            )

    def test_operator_session_tracks_scan_state(self):
        record = OperatorSessionRecord.model_validate(
            {
                "session_id": "session_scan_001",
                "principal_id": "operator_demo",
                "workspace": "console",
                "arrival_radius_feet": 75,
                "current_distance_feet": 42.0,
                "navigation_active": True,
                "scan_state": "active_lpr_scan",
                "scan_processing_mode": "realtime_lpr",
                "lpr_realtime_enabled": True,
                "vehicle_enrichment_deferred": True,
                "primary_ai_camera_id": "cam_lpr_primary",
                "secondary_context_camera_id": "cam_overview_context",
                "last_seen_at_utc": "2026-03-26T04:16:00Z",
            }
        )

        assert record.scan_state == ScanSessionState.active_lpr_scan
        assert record.scan_processing_mode == ScanProcessingMode.realtime_lpr
        assert record.lpr_realtime_enabled is True
