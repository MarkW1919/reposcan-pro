from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

from PIL import Image


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "launch_capture_detection_review_app.py"
    spec = importlib.util.spec_from_file_location("capture_detection_review_app", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 480), color=(32, 64, 96)).save(path)


def test_apply_form_to_row_normalizes_bbox_and_flags():
    module = _load_module()
    row = {
        "reposcan_accepted": "false",
        "reposcan_reviewed": "false",
        "class_label": "car",
        "bbox_x": "10",
        "bbox_y": "20",
        "bbox_w": "30",
        "bbox_h": "40",
    }

    updated = module.apply_form_to_row(
        row,
        accepted=True,
        reviewed=True,
        class_label="truck",
        bbox_x=15,
        bbox_y=25,
        bbox_w=35,
        bbox_h=45,
        reviewer_notes="checked",
    )

    assert updated["reposcan_accepted"] == "true"
    assert updated["reposcan_reviewed"] == "true"
    assert updated["class_label"] == "truck"
    assert updated["bbox_x"] == "15"
    assert updated["bbox_h"] == "45"


def test_render_crop_and_write_crop_from_row(tmp_path):
    module = _load_module()
    frame_path = tmp_path / "frames" / "frame_001.jpg"
    _write_image(frame_path)

    review_csv = tmp_path / "review" / "metadata" / "detection_review.csv"
    review_csv.parent.mkdir(parents=True, exist_ok=True)
    with review_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame_source_path", "frame_relative_path", "crop_relative_path", "bbox_x", "bbox_y", "bbox_w", "bbox_h"])
        writer.writerow([str(frame_path), "", "crops/vehicle/frame_001.jpg", "10", "20", "100", "80"])

    row = {
        "frame_source_path": str(frame_path),
        "frame_relative_path": "",
        "crop_relative_path": "crops/vehicle/frame_001.jpg",
        "bbox_x": "10",
        "bbox_y": "20",
        "bbox_w": "100",
        "bbox_h": "80",
    }

    crop = module.render_crop_preview(row)
    assert crop.size == (100, 80)

    crop_path = module.write_crop_from_row(review_csv, row)
    assert crop_path.exists()


def test_render_frame_overlay_uses_frame_source_path(tmp_path):
    module = _load_module()
    frame_path = tmp_path / "frames" / "frame_002.jpg"
    _write_image(frame_path)
    row = {
        "frame_source_path": str(frame_path),
        "bbox_x": "5",
        "bbox_y": "6",
        "bbox_w": "50",
        "bbox_h": "60",
        "class_label": "car",
        "confidence": "0.91",
        "reposcan_accepted": "false",
        "reposcan_reviewed": "false",
    }

    overlay = module.render_frame_overlay(row)
    assert overlay.size == (640, 480)
