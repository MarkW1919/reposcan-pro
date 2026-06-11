from __future__ import annotations

from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.inference import AttributePredictions, InferenceCandidate, ModelVersions
from reposcan_alerting import AlertingService
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService
from reposcan_tracking import TrackingService


def _frame(frame_number: int, timestamp_utc: str) -> FrameEnvelope:
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"frm_{frame_number:03d}",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": timestamp_utc,
            "frame_path": f"media/frames/cam_north_gate_01/frame_{frame_number:06d}.jpg",
            "frame_number": frame_number,
            "source_type": "rtsp",
            "camera_profile": CameraProfile(
                camera_id="cam_north_gate_01",
                source_type=SourceType.rtsp,
            ).model_dump(mode="json"),
        }
    )


def _candidate(timestamp_utc: str, plate_text: str, plate_confidence: float) -> InferenceCandidate:
    return InferenceCandidate.model_validate(
        {
            "frame_id": f"cand_{timestamp_utc}",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": timestamp_utc,
            "vehicle_detections": [
                {
                    "bbox": {"x": 410, "y": 220, "w": 300, "h": 180},
                    "confidence": 0.9,
                    "class_label": "car",
                }
            ],
            "plate_detections": [
                {
                    "bbox": {"x": 520, "y": 338, "w": 86, "h": 28},
                    "confidence": 0.91,
                    "vehicle_index": 0,
                }
            ],
            "ocr_candidates": [
                {"text": plate_text, "confidence": plate_confidence},
                {"text": "8A8C123", "confidence": 0.41},
            ],
            "attribute_predictions": [
                AttributePredictions(
                    color="white",
                    color_confidence=0.88,
                    make="toyota",
                    make_confidence=0.67,
                    model="camry",
                    model_confidence=0.54,
                ).model_dump(mode="json", by_alias=True)
            ],
            "model_versions": ModelVersions(vehicle_detector="vd", plate_detector="pd", ocr="ocr").model_dump(mode="json"),
            "processing_latency_ms": 12.5,
        }
    )


def _frame_with_gps(frame_number: int, timestamp_utc: str, lat: float, lon: float) -> FrameEnvelope:
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"frm_{frame_number:03d}",
            "camera_id": "cam_north_gate_01",
            "timestamp_utc": timestamp_utc,
            "frame_path": f"media/frames/cam_north_gate_01/frame_{frame_number:06d}.jpg",
            "frame_number": frame_number,
            "source_type": "rtsp",
            "gps_snapshot": {"latitude": lat, "longitude": lon},
            "camera_profile": CameraProfile(
                camera_id="cam_north_gate_01", source_type=SourceType.rtsp
            ).model_dump(mode="json"),
        }
    )


def test_detection_gps_propagates_and_drives_in_zone_lead(tmp_path):
    # Frames carry the unit's GPS; it must flow frame -> track -> DetectionRecord
    # (mission requirement) and then drive a geofenced make/model in-zone lead.
    from reposcan_alerting.geo import entries_within_zone

    target_lat, target_lon = 35.4676, -97.5164
    near_lat, near_lon = 35.46801, -97.5164  # ~150 ft from target

    tracking_service = TrackingService.from_config_path()
    tracking_service.pipeline_config.tracking.min_hits_to_confirm = 2
    tracking_service.pipeline_config.tracking.max_lost_frames = 0
    tracking_service.pipeline_config.fusion.min_ocr_candidates_for_promotion = 2

    frames = [
        _frame_with_gps(1, "2026-06-03T12:00:00Z", near_lat, near_lon),
        _frame_with_gps(2, "2026-06-03T12:00:01Z", near_lat, near_lon),
    ]
    candidates = [
        _candidate("2026-06-03T12:00:00Z", "PLATE01", 0.93),
        _candidate("2026-06-03T12:00:01Z", "PLATE01", 0.95),
    ]
    for frame, candidate in zip(frames, candidates):
        tracking_service.ingest(frame, candidate)
    tracked = tracking_service.flush()[0]

    # GPS carried onto the tracked detection.
    assert tracked.gps_latitude == near_lat
    assert tracked.gps_longitude == near_lon

    storage_service = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
    stored = storage_service.store_tracked_detection(tracked)
    # GPS persisted on the record (mission: store detections with GPS).
    assert stored.gps_latitude == near_lat
    assert stored.gps_longitude == near_lon

    # The candidate attributes are make=toyota model=camry; a make/model hotlist
    # at the target address fires an IN-ZONE LEAD using the stored detection GPS.
    entry = HotlistEntry.model_validate(
        {
            "entry_id": "hl_zone",
            "vehicle_make": "toyota",
            "vehicle_model": "camry",
            "address_latitude": target_lat,
            "address_longitude": target_lon,
            "label": "Zone target",
            "created_at_utc": "2026-06-03T11:00:00Z",
            "updated_at_utc": "2026-06-03T11:00:00Z",
        }
    )
    alerting_service = AlertingService.from_config_path()
    in_zone = entries_within_zone(stored.gps_latitude, stored.gps_longitude, [entry], radius_feet=300)
    alert = alerting_service.evaluate(tracked, [entry], in_zone_entry_ids=in_zone)
    assert alert is not None
    assert alert.match_kind.value == "in_zone_profile"
    assert "make" in alert.matched_attributes and "model" in alert.matched_attributes


def test_tracking_to_alerting_flow(tmp_path):
    tracking_service = TrackingService.from_config_path()
    tracking_service.pipeline_config.tracking.min_hits_to_confirm = 2
    tracking_service.pipeline_config.tracking.max_lost_frames = 0
    tracking_service.pipeline_config.fusion.min_ocr_candidates_for_promotion = 2

    frames = [
        _frame(1, "2026-03-20T12:00:00Z"),
        _frame(2, "2026-03-20T12:00:01Z"),
    ]
    candidates = [
        _candidate("2026-03-20T12:00:00Z", "8ABC123", 0.93),
        _candidate("2026-03-20T12:00:01Z", "8ABC123", 0.95),
    ]

    for frame, candidate in zip(frames, candidates):
        tracking_service.ingest(frame, candidate)

    tracked_detections = tracking_service.flush()

    assert len(tracked_detections) == 1
    tracked = tracked_detections[0]
    assert tracked.best_plate_candidate is not None
    assert tracked.best_plate_candidate.text == "8ABC123"
    assert tracked.confidence_summary.frames_tracked == 2
    assert tracked.evidence_refs.best_frame_path.endswith("frame_000002.jpg")

    storage_service = StorageService(
        repository=InMemoryStorageRepository(),
        media_root=tmp_path / "media",
    )
    stored_detection = storage_service.store_tracked_detection(tracked)
    assert stored_detection.plate_text == "8ABC123"

    hotlist = HotlistEntry.model_validate(
        {
            "entry_id": "hl_001",
            "plate_text": "8ABC123",
            "label": "Case 42",
            "created_at_utc": "2026-03-20T11:00:00Z",
            "updated_at_utc": "2026-03-20T11:00:00Z",
        }
    )
    storage_service.create_hotlist(hotlist)

    alerting_service = AlertingService.from_config_path()
    alert = alerting_service.evaluate(tracked, storage_service.list_hotlists(active_only=True))

    assert alert is not None
    storage_service.store_alert(alert)
    assert storage_service.list_alerts()[0].hotlist_entry_id == "hl_001"
