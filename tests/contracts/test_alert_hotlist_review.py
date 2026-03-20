"""Tests for alert, hotlist, and review contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.hotlist import HotlistEntry, HotlistMatchResult
from reposcan_contracts.review import ReviewAction, ReviewRecord
from reposcan_contracts.types import PlateMatchType


# ---------------------------------------------------------------------------
# AlertRecord
# ---------------------------------------------------------------------------

class TestAlertRecord:
    def _valid(self, **overrides) -> dict:
        base = {
            "alert_id": "alert_001",
            "detection_id": "det_001",
            "hotlist_entry_id": "hl_001",
            "timestamp_utc": "2026-03-19T22:10:00Z",
            "camera_id": "cam_north_gate_01",
            "matched_plate_text": "8ABC123",
            "match_confidence": 0.93,
            "match_type": "exact",
        }
        base.update(overrides)
        return base

    def test_valid_creates_active_alert(self):
        alert = AlertRecord.model_validate(self._valid())
        assert alert.status == AlertStatus.active

    def test_match_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            AlertRecord.model_validate(self._valid(match_confidence=1.5))

    def test_empty_plate_text_rejected(self):
        with pytest.raises(ValidationError):
            AlertRecord.model_validate(self._valid(matched_plate_text=""))

    def test_status_transitions_roundtrip(self):
        for status in AlertStatus:
            a = AlertRecord.model_validate(self._valid(status=status))
            assert a.status == status

    def test_invalid_match_type_rejected(self):
        with pytest.raises(ValidationError):
            AlertRecord.model_validate(self._valid(match_type="partial"))

    def test_non_utc_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            AlertRecord.model_validate(self._valid(timestamp_utc="2026-03-19T22:10:00-07:00"))


# ---------------------------------------------------------------------------
# HotlistEntry
# ---------------------------------------------------------------------------

class TestHotlistEntry:
    def _valid(self, **overrides) -> dict:
        base = {
            "entry_id": "hl_001",
            "plate_text": "8abc123",
            "created_at_utc": "2026-03-19T00:00:00Z",
            "updated_at_utc": "2026-03-19T00:00:00Z",
        }
        base.update(overrides)
        return base

    def test_plate_normalized_to_uppercase(self):
        entry = HotlistEntry.model_validate(self._valid(plate_text="8abc123"))
        assert entry.plate_text == "8ABC123"

    def test_whitespace_stripped_and_uppercased(self):
        entry = HotlistEntry.model_validate(self._valid(plate_text="  abc  "))
        assert entry.plate_text == "ABC"

    def test_default_active(self):
        entry = HotlistEntry.model_validate(self._valid())
        assert entry.active is True

    def test_empty_plate_rejected(self):
        with pytest.raises(ValidationError):
            HotlistEntry.model_validate(self._valid(plate_text="   "))

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            HotlistEntry.model_validate(self._valid(created_at_utc="not-a-timestamp"))


class TestHotlistMatchResult:
    def test_no_match(self):
        result = HotlistMatchResult(matched=False, plate_text="XYZ999")
        assert result.matched is False
        assert result.entry_id is None

    def test_match(self):
        result = HotlistMatchResult(
            matched=True,
            entry_id="hl_001",
            match_type="exact",
            plate_text="8ABC123",
        )
        assert result.match_type == PlateMatchType.exact

    def test_invalid_match_type_rejected(self):
        with pytest.raises(ValidationError):
            HotlistMatchResult(matched=True, entry_id="hl_001", match_type="partial", plate_text="8ABC123")


# ---------------------------------------------------------------------------
# ReviewRecord
# ---------------------------------------------------------------------------

class TestReviewRecord:
    def _valid(self, **overrides) -> dict:
        base = {
            "review_id": "rev_001",
            "detection_id": "det_001",
            "action": "confirm",
            "reviewed_at_utc": "2026-03-19T22:15:00Z",
        }
        base.update(overrides)
        return base

    def test_confirm_action(self):
        r = ReviewRecord.model_validate(self._valid())
        assert r.action == ReviewAction.confirm

    def test_correct_action_requires_corrected_text(self):
        with pytest.raises(ValidationError):
            ReviewRecord.model_validate(self._valid(action="correct"))

    def test_correct_action_with_text(self):
        r = ReviewRecord.model_validate(
            self._valid(action="correct", corrected_plate_text="8XYZ999")
        )
        assert r.corrected_plate_text == "8XYZ999"

    def test_all_actions_valid(self):
        for action in ReviewAction:
            data = self._valid(action=action)
            if action == ReviewAction.correct:
                data["corrected_plate_text"] = "8ABC123"
            r = ReviewRecord.model_validate(data)
            assert r.action == action

    def test_invalid_review_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            ReviewRecord.model_validate(self._valid(reviewed_at_utc="2026-03-19 22:15:00"))
