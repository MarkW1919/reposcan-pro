"""Seed helpers for the local development storage service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry

if TYPE_CHECKING:
    from .service import StorageService


def seed_development_operator_data(service: "StorageService") -> None:
    """Populate a fresh development store with operator-friendly demo data."""

    if service.list_detections(limit=1) or service.list_alerts(limit=1) or service.list_hotlists(limit=1):
        return

    detections = [
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_010001",
                "timestamp_utc": "2026-03-20T01:14:22Z",
                "camera_id": "cam_street_02",
                "gps_latitude": 37.42172,
                "gps_longitude": -122.08408,
                "plate_text": "6BZN220",
                "plate_confidence": 0.93,
                "plate_candidates": [{"text": "6BZN220", "confidence": 0.93}],
                "vehicle_bbox": {"x": 416, "y": 212, "w": 320, "h": 188},
                "plate_bbox": {"x": 524, "y": 336, "w": 94, "h": 30},
                "vehicle_color": "white",
                "vehicle_color_confidence": 0.89,
                "vehicle_make": "toyota",
                "vehicle_make_confidence": 0.82,
                "vehicle_model": "camry",
                "vehicle_model_confidence": 0.78,
                "optional_vehicle_year": "2018-2021",
                "optional_year_confidence": 0.66,
                "tracker_id": "trk_010001",
                "image_path": "media/frames/cam_street_02/frame_000812.jpg",
                "plate_crop_path": "media/crops/cam_street_02/plate_000812.jpg",
                "frame_number": 812,
            }
        ),
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_010002",
                "timestamp_utc": "2026-03-20T01:12:08Z",
                "camera_id": "cam_gate_north_01",
                "gps_latitude": 37.42243,
                "gps_longitude": -122.08229,
                "plate_text": "3LPM771",
                "plate_confidence": 0.89,
                "plate_candidates": [{"text": "3LPM771", "confidence": 0.89}],
                "vehicle_bbox": {"x": 388, "y": 204, "w": 336, "h": 194},
                "plate_bbox": {"x": 510, "y": 332, "w": 92, "h": 29},
                "vehicle_color": "black",
                "vehicle_color_confidence": 0.9,
                "vehicle_make": "ford",
                "vehicle_make_confidence": 0.8,
                "vehicle_model": "explorer",
                "vehicle_model_confidence": 0.76,
                "optional_vehicle_year": "2019-2023",
                "optional_year_confidence": 0.63,
                "tracker_id": "trk_010002",
                "image_path": "media/frames/cam_gate_north_01/frame_000731.jpg",
                "plate_crop_path": "media/crops/cam_gate_north_01/plate_000731.jpg",
                "frame_number": 731,
            }
        ),
        DetectionRecord.model_validate(
            {
                "detection_id": "det_20260320_010003",
                "timestamp_utc": "2026-03-20T01:09:44Z",
                "camera_id": "cam_lot_east_03",
                "gps_latitude": 37.42061,
                "gps_longitude": -122.08155,
                "plate_text": "9XCA441",
                "plate_confidence": 0.86,
                "plate_candidates": [{"text": "9XCA441", "confidence": 0.86}],
                "vehicle_bbox": {"x": 404, "y": 218, "w": 314, "h": 186},
                "plate_bbox": {"x": 520, "y": 334, "w": 88, "h": 28},
                "vehicle_color": "gray",
                "vehicle_color_confidence": 0.87,
                "vehicle_make": "honda",
                "vehicle_make_confidence": 0.77,
                "vehicle_model": "accord",
                "vehicle_model_confidence": 0.74,
                "optional_vehicle_year": "2017-2020",
                "optional_year_confidence": 0.61,
                "tracker_id": "trk_010003",
                "image_path": "media/frames/cam_lot_east_03/frame_000644.jpg",
                "plate_crop_path": "media/crops/cam_lot_east_03/plate_000644.jpg",
                "frame_number": 644,
            }
        ),
    ]

    hotlists = [
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_20260320_000001",
                "plate_text": "6BZN220",
                "label": "Marina tow-ready",
                "notes": "Primary recovery target",
                "created_at_utc": "2026-03-20T00:45:00Z",
                "updated_at_utc": "2026-03-20T00:45:00Z",
            }
        ),
        HotlistEntry.model_validate(
            {
                "entry_id": "hl_20260320_000002",
                "plate_text": "9XCA441",
                "label": "Lot east watch",
                "notes": "Confirm rear plate before hook",
                "created_at_utc": "2026-03-20T00:50:00Z",
                "updated_at_utc": "2026-03-20T00:50:00Z",
            }
        ),
    ]

    alerts = [
        AlertRecord.model_validate(
            {
                "alert_id": "alert_20260320_000001",
                "detection_id": "det_20260320_010001",
                "hotlist_entry_id": "hl_20260320_000001",
                "timestamp_utc": "2026-03-20T01:14:25Z",
                "camera_id": "cam_street_02",
                "matched_plate_text": "6BZN220",
                "match_confidence": 0.93,
                "match_type": "exact",
                "hotlist_label": "Marina tow-ready",
                "notes": "Vehicle parked nose-out near south fence line.",
                "gps_latitude": 37.42172,
                "gps_longitude": -122.08408,
            }
        ),
        AlertRecord.model_validate(
            {
                "alert_id": "alert_20260320_000002",
                "detection_id": "det_20260320_010003",
                "hotlist_entry_id": "hl_20260320_000002",
                "timestamp_utc": "2026-03-20T01:09:47Z",
                "camera_id": "cam_lot_east_03",
                "matched_plate_text": "9XCA441",
                "match_confidence": 0.9,
                "match_type": "exact",
                "hotlist_label": "Lot east watch",
                "notes": "Photo match is strong. Confirm before engagement.",
                "gps_latitude": 37.42061,
                "gps_longitude": -122.08155,
            }
        ),
    ]

    for detection in detections:
        service.store_detection(detection)

    for hotlist in hotlists:
        service.create_hotlist(hotlist)

    for alert in alerts:
        service.store_alert(alert)
