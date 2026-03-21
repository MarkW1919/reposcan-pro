"""Tests for inter-service contracts: FrameEnvelope, InferenceCandidate, TrackedDetection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reposcan_contracts.frame import (
    CameraProfile,
    FrameEnvelope,
    GpsSnapshot,
    PreparedFrame,
    PreprocessingMetadata,
    SourceType,
)
from reposcan_contracts.inference import (
    AttributePredictions,
    InferenceCandidate,
    ModelVersions,
    PlateDetection,
    VehicleDetection,
)
from reposcan_contracts.tracking import ConfidenceSummary, EvidenceRefs, TrackedDetection
from reposcan_contracts.detection import BoundingBox, PlateCandidate


# ---------------------------------------------------------------------------
# FrameEnvelope
# ---------------------------------------------------------------------------

class TestFrameEnvelope:
    def _profile(self) -> CameraProfile:
        return CameraProfile(
            camera_id="cam_north_gate_01",
            source_type=SourceType.rtsp,
        )

    def _valid(self, **overrides) -> dict:
        base = {
            "frame_id": "frm_001",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": "2026-03-19T22:10:00Z",
            "frame_path": "/data/frames/frm_001.jpg",
            "frame_number": 0,
            "source_type": "rtsp",
            "camera_profile": self._profile().model_dump(),
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        env = FrameEnvelope.model_validate(self._valid())
        assert env.frame_id == "frm_001"
        assert env.gps_snapshot is None

    def test_with_gps(self):
        data = self._valid()
        data["gps_snapshot"] = {"latitude": 34.12345, "longitude": -118.12345}
        env = FrameEnvelope.model_validate(data)
        assert env.gps_snapshot.latitude == pytest.approx(34.12345)

    def test_negative_frame_number_rejected(self):
        with pytest.raises(ValidationError):
            FrameEnvelope.model_validate(self._valid(frame_number=-1))

    def test_gps_latitude_bounds(self):
        data = self._valid()
        data["gps_snapshot"] = {"latitude": 91.0, "longitude": 0.0}
        with pytest.raises(ValidationError):
            FrameEnvelope.model_validate(data)

    def test_source_type_enum(self):
        for st in SourceType:
            env = FrameEnvelope.model_validate(self._valid(source_type=st.value))
            assert env.source_type == st

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            FrameEnvelope.model_validate(self._valid(timestamp_utc="bad-timestamp"))


class TestPreparedFrame:
    def _profile(self) -> CameraProfile:
        return CameraProfile(
            camera_id="cam_north_gate_01",
            source_type=SourceType.file,
            ir_mode=True,
        )

    def _valid(self, **overrides) -> dict:
        base = {
            "frame_id": "frm_001",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": "2026-03-19T22:10:00Z",
            "raw_frame_path": "/data/frames/frm_001.jpg",
            "prepared_frame_path": "/data/preprocessed/frm_001_prepared.jpg",
            "frame_number": 0,
            "source_type": "file",
            "camera_profile": self._profile().model_dump(mode="json"),
            "preprocessing": PreprocessingMetadata(
                artifact_generated=True,
                denoise_applied=True,
                contrast_enhanced=True,
                night_mode_triggered=True,
                mean_brightness_before=22.0,
                mean_brightness_after=58.0,
            ).model_dump(mode="json"),
        }
        base.update(overrides)
        return base

    def test_valid_prepared_frame(self):
        env = PreparedFrame.model_validate(self._valid())
        assert env.raw_frame_path.endswith("frm_001.jpg")
        assert env.preprocessing.artifact_generated is True

    def test_brightness_bounds_rejected(self):
        with pytest.raises(ValidationError):
            PreparedFrame.model_validate(
                self._valid(preprocessing={"mean_brightness_before": 999.0})
            )


# ---------------------------------------------------------------------------
# InferenceCandidate
# ---------------------------------------------------------------------------

class TestInferenceCandidate:
    def _valid(self, **overrides) -> dict:
        base = {
            "frame_id": "frm_001",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": "2026-03-19T22:10:00Z",
            "processing_latency_ms": 42.5,
        }
        base.update(overrides)
        return base

    def test_valid_empty_detections(self):
        cand = InferenceCandidate.model_validate(self._valid())
        assert cand.vehicle_detections == []
        assert cand.plate_detections == []
        assert cand.ocr_candidates == []

    def test_with_vehicle_and_plate(self):
        data = self._valid()
        data["vehicle_detections"] = [
            {"bbox": {"x": 412, "y": 220, "w": 301, "h": 184}, "confidence": 0.85, "class_label": "car"}
        ]
        data["plate_detections"] = [
            {"bbox": {"x": 518, "y": 338, "w": 86, "h": 28}, "confidence": 0.92}
        ]
        data["ocr_candidates"] = [{"text": "8ABC123", "confidence": 0.93}]
        cand = InferenceCandidate.model_validate(data)
        assert len(cand.vehicle_detections) == 1
        assert cand.vehicle_detections[0].class_label == "car"
        assert cand.ocr_candidates[0].text == "8ABC123"

    def test_negative_latency_rejected(self):
        with pytest.raises(ValidationError):
            InferenceCandidate.model_validate(self._valid(processing_latency_ms=-1.0))

    def test_model_versions_defaults(self):
        cand = InferenceCandidate.model_validate(self._valid())
        assert cand.model_versions.vehicle_detector is None

    def test_attribute_predictions_alias(self):
        attrs = AttributePredictions.model_validate({
            "color": "white",
            "color_confidence": 0.88,
            "model": "camry",
            "model_confidence": 0.54,
        })
        assert attrs.model_label == "camry"

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            InferenceCandidate.model_validate(self._valid(timestamp_utc="2026-03-19 22:10:00"))


# ---------------------------------------------------------------------------
# TrackedDetection
# ---------------------------------------------------------------------------

class TestTrackedDetection:
    def _valid(self, **overrides) -> dict:
        base = {
            "detection_id": "det_001",
            "tracker_id": "trk_2048",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": "2026-03-19T22:10:00Z",
            "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
            "frame_number": 542,
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        td = TrackedDetection.model_validate(self._valid())
        assert td.detection_id == "det_001"
        assert td.best_plate_candidate is None
        assert td.alternate_plate_candidates == []

    def test_with_best_plate(self):
        data = self._valid()
        data["best_plate_candidate"] = {"text": "8ABC123", "confidence": 0.93}
        td = TrackedDetection.model_validate(data)
        assert td.best_plate_candidate.text == "8ABC123"

    def test_confidence_summary_defaults(self):
        td = TrackedDetection.model_validate(self._valid())
        assert td.confidence_summary.frames_tracked == 0
        assert td.confidence_summary.ocr_candidate_count == 0

    def test_evidence_refs_defaults(self):
        td = TrackedDetection.model_validate(self._valid())
        assert td.evidence_refs.best_frame_path is None

    def test_negative_frame_number_rejected(self):
        with pytest.raises(ValidationError):
            TrackedDetection.model_validate(self._valid(frame_number=-1))

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            TrackedDetection.model_validate(self._valid(timestamp_utc="2026-03-19 22:10:00"))
