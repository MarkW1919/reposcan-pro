from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path

from PIL import Image


def _load_labeler_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "label_vehicle_attribute_crops_with_vlm.py"
    spec = importlib.util.spec_from_file_location("vehicle_vlm_attribute_labeler", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_crop_review_csv(path: Path, crop_path: Path) -> None:
    fieldnames = [
        "crop_id",
        "source_sample_id",
        "source_filepath",
        "crop_filepath",
        "source_label",
        "bbox_x",
        "bbox_y",
        "bbox_w",
        "bbox_h",
        "crop_width",
        "crop_height",
        "reposcan_accepted",
        "reposcan_reviewed",
        "reposcan_class_label",
        "reposcan_vehicle_make",
        "reposcan_vehicle_model",
        "reposcan_vehicle_year",
        "reposcan_vehicle_color",
        "reposcan_oklahoma_tags",
        "reviewer_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "crop_id": "crop_f150",
                "source_sample_id": "source_1",
                "source_filepath": "source_a.jpg",
                "crop_filepath": str(crop_path),
                "source_label": "Truck",
                "bbox_x": "0",
                "bbox_y": "0",
                "bbox_w": "1",
                "bbox_h": "1",
                "crop_width": "96",
                "crop_height": "64",
                "reposcan_accepted": "false",
                "reposcan_reviewed": "false",
            }
        )


def test_vlm_label_crops_adds_fixture_suggestions(tmp_path):
    module = _load_labeler_module()
    crop_path = tmp_path / "f150.jpg"
    Image.new("RGB", (96, 64), color=(8, 8, 8)).save(crop_path)
    review_csv = tmp_path / "crop_review.csv"
    output_csv = tmp_path / "vlm_suggestions.csv"
    fixture_jsonl = tmp_path / "fixture.jsonl"
    _write_crop_review_csv(review_csv, crop_path)
    fixture_jsonl.write_text(
        json.dumps(
            {
                "crop_id": "crop_f150",
                "response": {
                    "contains_usable_vehicle": True,
                    "make": "Ford",
                    "model": "F-150",
                    "model_family": "F-Series",
                    "year": 2020,
                    "year_range": "2018-2020",
                    "trim": "Lariat",
                    "color": "black",
                    "body_type": "pickup",
                    "confidence": 0.91,
                    "evidence": "front grille and badging",
                    "review_action": "accept_suggestion",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = module.label_crops(
        argparse.Namespace(
            review_csv=str(review_csv),
            output_csv=str(output_csv),
            provider="fixture",
            model=None,
            fixture_jsonl=str(fixture_jsonl),
            limit=None,
            skip_existing=False,
            overwrite=False,
            progress_every=0,
            max_new_tokens=360,
            device_map="auto",
            temperature=0.0,
            openai_api_key_env="OPENAI_API_KEY",
        )
    )

    assert result == 0
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8", newline="")))
    assert rows[0]["suggested_vlm_provider"] == "fixture"
    assert rows[0]["suggested_vlm_vehicle_make"] == "ford"
    assert rows[0]["suggested_vlm_vehicle_model"] == "f_150"
    assert rows[0]["suggested_vlm_vehicle_model_family"] == "f_series"
    assert rows[0]["suggested_vlm_vehicle_color"] == "black"
    assert rows[0]["suggested_vlm_contains_usable_vehicle"] == "true"
    assert rows[0]["vlm_label_error"] == ""


def test_apply_consensus_marks_pending_make_model_rows(tmp_path):
    module = _load_labeler_module()
    input_csv = tmp_path / "vlm_suggestions.csv"
    output_csv = tmp_path / "consensus.csv"
    fieldnames = [
        "crop_id",
        "reposcan_accepted",
        "reposcan_reviewed",
        "reposcan_class_label",
        "reposcan_vehicle_make",
        "reposcan_vehicle_model",
        "reposcan_vehicle_year",
        "reposcan_vehicle_color",
        "reposcan_oklahoma_tags",
        "reviewer_notes",
        "suggested_vlm_provider",
        "suggested_vlm_contains_usable_vehicle",
        "suggested_vlm_vehicle_make",
        "suggested_vlm_vehicle_model",
        "suggested_vlm_vehicle_model_family",
        "suggested_vlm_body_type",
        "suggested_vlm_confidence",
        "suggested_vlm_review_action",
        "suggested_make_model_top1_confidence",
    ]
    with input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "crop_id": "crop_f150",
                "reposcan_accepted": "false",
                "reposcan_reviewed": "false",
                "suggested_vlm_provider": "fixture",
                "suggested_vlm_contains_usable_vehicle": "true",
                "suggested_vlm_vehicle_make": "ford",
                "suggested_vlm_vehicle_model": "f_150",
                "suggested_vlm_vehicle_model_family": "f_series",
                "suggested_vlm_body_type": "pickup",
                "suggested_vlm_confidence": "0.91",
                "suggested_vlm_review_action": "accept_suggestion",
                "suggested_make_model_top1_confidence": "0.20",
            }
        )

    result = module.apply_consensus(
        argparse.Namespace(
            input_csv=str(input_csv),
            output_csv=str(output_csv),
            task="vehicle_make_model_classification",
            min_vlm_confidence=0.75,
            min_color_confidence=0.70,
            min_onnx_confidence=0.75,
            min_year_confidence=0.90,
            allow_year_range=False,
            allow_vlm_overrides_onnx=False,
            mark_reviewed=False,
            overwrite=False,
        )
    )

    assert result == 0
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8", newline="")))
    row = rows[0]
    assert row["reposcan_accepted"] == "true"
    assert row["reposcan_reviewed"] == "false"
    assert row["reposcan_class_label"] == "ford_f_series"
    assert row["reposcan_vehicle_make"] == "ford"
    assert row["reposcan_vehicle_model"] == "f_series"
    assert "vehicle_class:pickup" in row["reposcan_oklahoma_tags"]
    assert "ai_assisted_consensus_pending_review:fixture" in row["reviewer_notes"]


def test_apply_consensus_skips_color_conflicts(tmp_path):
    module = _load_labeler_module()
    input_csv = tmp_path / "vlm_suggestions.csv"
    output_csv = tmp_path / "consensus.csv"
    fieldnames = [
        "crop_id",
        "reposcan_accepted",
        "reposcan_reviewed",
        "reposcan_vehicle_color",
        "reviewer_notes",
        "suggested_vehicle_color",
        "suggested_vehicle_color_confidence",
        "suggested_vlm_contains_usable_vehicle",
        "suggested_vlm_vehicle_color",
        "suggested_vlm_confidence",
        "suggested_vlm_review_action",
    ]
    with input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "crop_id": "crop_color_conflict",
                "reposcan_accepted": "false",
                "reposcan_reviewed": "false",
                "suggested_vehicle_color": "black",
                "suggested_vehicle_color_confidence": "0.92",
                "suggested_vlm_contains_usable_vehicle": "true",
                "suggested_vlm_vehicle_color": "blue",
                "suggested_vlm_confidence": "0.90",
                "suggested_vlm_review_action": "accept_suggestion",
            }
        )

    result = module.apply_consensus(
        argparse.Namespace(
            input_csv=str(input_csv),
            output_csv=str(output_csv),
            task="vehicle_color_classification",
            min_vlm_confidence=0.75,
            min_color_confidence=0.70,
            min_onnx_confidence=0.75,
            min_year_confidence=0.90,
            allow_year_range=False,
            allow_vlm_overrides_onnx=False,
            mark_reviewed=False,
            overwrite=False,
        )
    )

    assert result == 0
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8", newline="")))
    assert rows[0]["reposcan_accepted"] == "false"
    assert rows[0]["reposcan_vehicle_color"] == ""
    assert "color_consensus_conflict" in rows[0]["reviewer_notes"]
