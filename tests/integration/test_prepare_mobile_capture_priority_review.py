from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "prepare_mobile_capture_priority_review.py"
    spec = importlib.util.spec_from_file_location("prepare_mobile_capture_priority_review", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_plate_priority_rows_reduces_duplicate_ocr_groups():
    module = _load_module()
    rows = [
        {"detection_kind": "plate", "ocr_text": "ABC123", "ocr_confidence": "0.90", "confidence": "0.80", "timestamp_utc": "2026-04-19T18:00:01Z"},
        {"detection_kind": "plate", "ocr_text": "ABC123", "ocr_confidence": "0.95", "confidence": "0.70", "timestamp_utc": "2026-04-19T18:00:02Z"},
        {"detection_kind": "plate", "ocr_text": "XYZ999", "ocr_confidence": "0.50", "confidence": "0.60", "timestamp_utc": "2026-04-19T18:00:03Z"},
        {"detection_kind": "vehicle", "ocr_text": "", "ocr_confidence": "", "confidence": "0.99", "timestamp_utc": "2026-04-19T18:00:04Z"},
    ]

    prioritized = module.build_plate_priority_rows(rows, max_per_group=1, min_ocr_confidence=None)

    assert len(prioritized) == 2
    assert prioritized[0]["ocr_text"] == "ABC123"
    assert prioritized[0]["priority_group_key"] == "abc123"
    assert prioritized[0]["priority_group_size"] == "2"
    assert prioritized[1]["priority_group_key"] == "xyz999"


def test_build_vehicle_priority_rows_prefers_accept_suggestions():
    module = _load_module()
    rows = [
        {
            "source_label": "Car",
            "suggested_vlm_vehicle_make": "Ford",
            "suggested_vlm_vehicle_model": "Mustang",
            "suggested_vlm_vehicle_model_family": "",
            "suggested_vlm_body_type": "coupe",
            "suggested_vlm_review_action": "needs_human_review",
            "suggested_vlm_confidence": "0.91",
            "timestamp_utc": "2026-04-19T18:00:01Z",
        },
        {
            "source_label": "Car",
            "suggested_vlm_vehicle_make": "Ford",
            "suggested_vlm_vehicle_model": "Mustang",
            "suggested_vlm_vehicle_model_family": "",
            "suggested_vlm_body_type": "coupe",
            "suggested_vlm_review_action": "accept_suggestion",
            "suggested_vlm_confidence": "0.81",
            "timestamp_utc": "2026-04-19T18:00:02Z",
        },
        {
            "source_label": "Truck",
            "suggested_vlm_vehicle_make": "",
            "suggested_vlm_vehicle_model": "",
            "suggested_vlm_vehicle_model_family": "",
            "suggested_vlm_body_type": "pickup",
            "suggested_vlm_review_action": "needs_human_review",
            "suggested_vlm_confidence": "0.77",
            "timestamp_utc": "2026-04-19T18:00:03Z",
        },
    ]

    prioritized = module.build_vehicle_priority_rows(
        rows,
        max_per_group=1,
        min_vlm_confidence=None,
        prefer_accept_suggestions=True,
    )

    assert len(prioritized) == 2
    mustang = next(row for row in prioritized if row["priority_group_key"] == "ford_mustang")
    assert mustang["suggested_vlm_review_action"] == "accept_suggestion"
    pickup = next(row for row in prioritized if row["priority_group_key"] == "body_pickup")
    assert pickup["priority_group_size"] == "1"
