from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "prepare_mobile_capture_attribute_review.py"
    spec = importlib.util.spec_from_file_location("prepare_mobile_capture_attribute_review", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_attribute_review_rows_filters_plate_rows_and_maps_vehicle_fields(tmp_path):
    module = _load_module()
    detection_review_csv = tmp_path / "review" / "metadata" / "detection_review.csv"
    crop_root = detection_review_csv.parent.parent / "crops" / "vehicle" / "session_a"
    crop_root.mkdir(parents=True, exist_ok=True)
    crop_path = crop_root / "asset_001_vehicle_0.jpg"
    crop_path.write_bytes(b"fake")

    detection_rows = [
        {
            "asset_id": "asset_001",
            "detection_kind": "vehicle",
            "detection_index": "0",
            "crop_relative_path": "crops/vehicle/session_a/asset_001_vehicle_0.jpg",
            "class_label": "truck",
            "confidence": "0.91",
            "frame_source_path": "C:/captures/frame.jpg",
            "frame_relative_path": "raw/2026-04-19/session_a/frame.jpg",
            "metadata_relative_path": "raw/2026-04-19/session_a/frame.json",
            "capture_session_id": "session_a",
            "timestamp_utc": "2026-04-19T18:00:00Z",
            "bbox_x": "10",
            "bbox_y": "20",
            "bbox_w": "100",
            "bbox_h": "80",
            "suggested_color": "black",
            "suggested_color_confidence": "0.80",
            "suggested_make": "Ford",
            "suggested_make_confidence": "0.75",
            "suggested_model": "F-150",
            "suggested_model_confidence": "0.82",
            "suggested_year": "2020",
            "suggested_year_confidence": "0.44",
            "vehicle_detector_provider": "ultralytics-coco",
            "attribute_provider": "runtime",
            "reposcan_accepted": "false",
            "reposcan_reviewed": "false",
        },
        {
            "asset_id": "asset_002",
            "detection_kind": "plate",
            "detection_index": "0",
            "crop_relative_path": "crops/plate/session_a/asset_002_plate_0.jpg",
        },
    ]

    rows = module.build_attribute_review_rows(
        detection_rows,
        detection_review_csv=detection_review_csv,
        min_confidence=None,
        accepted_only=False,
        skip_reviewed=False,
        priority_reason="mobile_capture_vehicle_detection",
        drop_runtime_attribute_suggestions=False,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["crop_id"] == "asset_001_vehicle_0"
    assert row["crop_filepath"] == str(crop_path.resolve())
    assert row["source_label"] == "Truck"
    assert row["suggested_vehicle_make"] == "ford"
    assert row["suggested_vehicle_model"] == "f_150"
    assert row["suggested_make_model_top1"] == "ford_f_150"
    assert row["suggested_make_model_top1_confidence"] == "0.7500"


def test_build_attribute_review_rows_can_drop_runtime_attribute_suggestions(tmp_path):
    module = _load_module()
    detection_review_csv = tmp_path / "review" / "metadata" / "detection_review.csv"
    detection_rows = [
        {
            "asset_id": "asset_001",
            "detection_kind": "vehicle",
            "detection_index": "0",
            "crop_relative_path": "crops/vehicle/session_a/asset_001_vehicle_0.jpg",
            "class_label": "truck",
            "confidence": "0.91",
            "suggested_color": "white",
            "suggested_make": "Toyota",
            "suggested_model": "Camry",
            "suggested_make_confidence": "0.99",
            "suggested_model_confidence": "0.99",
            "suggested_year": "2018",
            "suggested_year_confidence": "0.99",
        }
    ]

    rows = module.build_attribute_review_rows(
        detection_rows,
        detection_review_csv=detection_review_csv,
        min_confidence=None,
        accepted_only=False,
        skip_reviewed=False,
        priority_reason="mobile_capture_vehicle_detection",
        drop_runtime_attribute_suggestions=True,
    )

    assert rows[0]["suggested_vehicle_color"] == ""
    assert rows[0]["suggested_vehicle_make"] == ""
    assert rows[0]["suggested_vehicle_model"] == ""
    assert rows[0]["suggested_make_model_top1"] == ""
    assert rows[0]["suggested_vehicle_year"] == ""


def test_main_writes_output_csv(tmp_path, monkeypatch):
    module = _load_module()
    detection_review_csv = tmp_path / "review" / "metadata" / "detection_review.csv"
    detection_review_csv.parent.mkdir(parents=True, exist_ok=True)
    crop_path = detection_review_csv.parent.parent / "crops" / "vehicle" / "session_a" / "asset_001_vehicle_0.jpg"
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    crop_path.write_bytes(b"fake")

    with detection_review_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "asset_id",
                "detection_kind",
                "detection_index",
                "crop_relative_path",
                "class_label",
                "confidence",
                "suggested_make",
                "suggested_make_confidence",
                "suggested_model",
                "suggested_model_confidence",
            ]
        )
        writer.writerow(
            [
                "asset_001",
                "vehicle",
                "0",
                "crops/vehicle/session_a/asset_001_vehicle_0.jpg",
                "car",
                "0.88",
                "Honda",
                "0.81",
                "Civic",
                "0.84",
            ]
        )

    output_csv = tmp_path / "vehicle_attribute_review.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "prepare_mobile_capture_attribute_review.py",
            "--detection-review-csv",
            str(detection_review_csv),
            "--output-csv",
            str(output_csv),
            "--overwrite",
        ],
    )

    assert module.main() == 0
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8", newline="")))
    assert len(rows) == 1
    assert rows[0]["source_label"] == "Car"
    assert rows[0]["suggested_make_model_top1"] == "honda_civic"
