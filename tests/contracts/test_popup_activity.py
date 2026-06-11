from __future__ import annotations

import pytest
from pydantic import ValidationError

from reposcan_contracts.popup import PopupActivityEvent, PopupEventType


def _valid_popup(**overrides) -> dict:
    base = {
        "event_id": "popup_alert_001",
        "event_type": "hotlist",
        "source_record_id": "alert_001",
        "detection_id": "det_001",
        "timestamp_utc": "2026-03-20T01:14:25Z",
        "camera_id": "cam_street_02",
        "plate_text": "6BZN220",
        "confidence": 0.93,
        "vehicle_color": "white",
        "vehicle_make": "toyota",
        "vehicle_model": "camry",
        "optional_vehicle_year": "2018-2021",
        "hotlist_label": "Marina tow-ready",
        "gps_latitude": 37.42172,
        "gps_longitude": -122.08408,
        "note": "Vehicle parked nose-out near south fence line.",
    }
    base.update(overrides)
    return base


def test_popup_activity_accepts_hotlist_payload():
    event = PopupActivityEvent.model_validate(_valid_popup())

    assert event.event_type == PopupEventType.hotlist
    assert event.hotlist_label == "Marina tow-ready"


def test_popup_activity_accepts_address_payload_without_plate():
    event = PopupActivityEvent.model_validate(
        _valid_popup(
            event_id="popup_det_001",
            event_type="address",
            source_record_id="det_001",
            plate_text=None,
            confidence=0.0,
            hotlist_label=None,
        )
    )

    assert event.event_type == PopupEventType.address
    assert event.plate_text is None


def test_popup_activity_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        PopupActivityEvent.model_validate(_valid_popup(confidence=1.5))
