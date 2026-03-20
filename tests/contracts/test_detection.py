"""Tests for the DetectionRecord contract.

These tests lock the shape and validation rules defined in API_CONTRACTS.md.
Any change to field names, types, or constraints must also update these tests.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reposcan_contracts.detection import BoundingBox, DetectionRecord, PlateCandidate, SyncStatus


class TestBoundingBox:
    def test_valid(self):
        bb = BoundingBox(x=10, y=20, w=100, h=50)
        assert bb.x == 10
        assert bb.w == 100

    def test_negative_origin_rejected(self):
        with pytest.raises(ValidationError):
            BoundingBox(x=-1, y=0, w=10, h=10)

    def test_zero_width_rejected(self):
        with pytest.raises(ValidationError):
            BoundingBox(x=0, y=0, w=0, h=10)

    def test_zero_height_rejected(self):
        with pytest.raises(ValidationError):
            BoundingBox(x=0, y=0, w=10, h=0)


class TestPlateCandidate:
    def test_valid(self):
        c = PlateCandidate(text="8ABC123", confidence=0.93)
        assert c.text == "8ABC123"

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            PlateCandidate(text="", confidence=0.5)

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            PlateCandidate(text="X", confidence=1.1)


class TestSyncStatus:
    def test_all_values_defined(self):
        assert set(SyncStatus) == {"pending", "synced", "failed", "skipped"}


class TestDetectionRecord:
    def test_minimal_valid(self, minimal_detection_data):
        det = DetectionRecord.model_validate(minimal_detection_data)
        assert det.detection_id == "det_20260319_000001"
        assert det.local_only_flag is True
        assert det.sync_status == SyncStatus.pending
        assert det.plate_candidates == []

    def test_full_payload_from_api_contracts_example(self, full_detection_data):
        det = DetectionRecord.model_validate(full_detection_data)
        assert det.plate_text == "8ABC123"
        assert det.plate_confidence == 0.93
        assert len(det.plate_candidates) == 2
        assert det.vehicle_color == "white"
        assert det.gps_latitude == pytest.approx(34.12345)

    def test_roundtrip_json(self, full_detection_data):
        det = DetectionRecord.model_validate(full_detection_data)
        restored = DetectionRecord.model_validate_json(det.model_dump_json())
        assert restored == det

    def test_plate_confidence_without_text_rejected(self, minimal_detection_data):
        minimal_detection_data["plate_confidence"] = 0.9
        # plate_text is absent — validator should reject
        with pytest.raises(ValidationError):
            DetectionRecord.model_validate(minimal_detection_data)

    def test_gps_latitude_out_of_range_rejected(self, minimal_detection_data):
        minimal_detection_data["gps_latitude"] = 91.0
        with pytest.raises(ValidationError):
            DetectionRecord.model_validate(minimal_detection_data)

    def test_frame_number_negative_rejected(self, minimal_detection_data):
        minimal_detection_data["frame_number"] = -1
        with pytest.raises(ValidationError):
            DetectionRecord.model_validate(minimal_detection_data)

    def test_default_sync_status_is_pending(self, minimal_detection_data):
        det = DetectionRecord.model_validate(minimal_detection_data)
        assert det.sync_status == SyncStatus.pending

    def test_schema_contains_all_api_contract_fields(self):
        fields = DetectionRecord.model_fields.keys()
        required_fields = {
            "detection_id", "timestamp_utc", "camera_id",
            "plate_text", "plate_confidence", "plate_candidates",
            "vehicle_bbox", "plate_bbox",
            "vehicle_color", "vehicle_color_confidence",
            "vehicle_make", "vehicle_make_confidence",
            "vehicle_model", "vehicle_model_confidence",
            "optional_vehicle_year", "optional_year_confidence",
            "tracker_id", "image_path", "plate_crop_path",
            "source_video_path", "frame_number",
            "local_only_flag", "sync_status",
        }
        missing = required_fields - set(fields)
        assert missing == set(), f"Missing fields in DetectionRecord: {missing}"
