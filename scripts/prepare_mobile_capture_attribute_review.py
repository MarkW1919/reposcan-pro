from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


OUTPUT_FIELDNAMES = [
    "crop_id",
    "crop_filepath",
    "source_label",
    "priority_reason",
    "frame_source_path",
    "frame_relative_path",
    "metadata_relative_path",
    "capture_session_id",
    "timestamp_utc",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "suggested_vehicle_color",
    "suggested_vehicle_color_confidence",
    "suggested_vehicle_make",
    "suggested_vehicle_model",
    "suggested_make_model_top1",
    "suggested_make_model_top1_confidence",
    "suggested_vehicle_year",
    "suggested_vehicle_year_confidence",
    "vehicle_detector_provider",
    "attribute_provider",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a vehicle-attribute review CSV from a mobile-capture detection review CSV."
    )
    parser.add_argument("--detection-review-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--min-confidence", type=float)
    parser.add_argument("--accepted-only", action="store_true")
    parser.add_argument("--skip-reviewed", action="store_true")
    parser.add_argument("--priority-reason", default="mobile_capture_vehicle_detection")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _slugify(value: Any) -> str:
    text = _clean_text(value).lower()
    chars = [character if character.isalnum() else "_" for character in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or ""


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return _clean_text(value).lower() in {"1", "true", "yes", "y", "accepted", "approved"}


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _output_root_from_detection_csv(detection_review_csv: Path) -> Path:
    return detection_review_csv.parent.parent


def _source_label_from_detection_class(class_label: str) -> str:
    slug = _slugify(class_label)
    mapping = {
        "car": "Car",
        "truck": "Truck",
        "bus": "Bus",
        "motorcycle": "Motorcycle",
        "van": "Van",
        "minivan": "Van",
        "suv": "Car",
        "pickup": "Truck",
    }
    return mapping.get(slug, "Car")


def _make_model_top1(row: dict[str, str]) -> tuple[str, str]:
    make = _slugify(row.get("suggested_make"))
    model = _slugify(row.get("suggested_model"))
    make_confidence = _coerce_float(row.get("suggested_make_confidence"))
    model_confidence = _coerce_float(row.get("suggested_model_confidence"))
    confidences = [value for value in (make_confidence, model_confidence) if value is not None]
    top_confidence = min(confidences) if confidences else None
    top_label = ""
    if make and model:
        top_label = f"{make}_{model}"
    elif model:
        top_label = model
    return top_label, (f"{top_confidence:.4f}" if top_confidence is not None else "")


def build_attribute_review_rows(
    detection_rows: list[dict[str, str]],
    *,
    detection_review_csv: Path,
    min_confidence: float | None,
    accepted_only: bool,
    skip_reviewed: bool,
    priority_reason: str,
) -> list[dict[str, str]]:
    output_root = _output_root_from_detection_csv(detection_review_csv)
    rows: list[dict[str, str]] = []
    for detection_row in detection_rows:
        if _clean_text(detection_row.get("detection_kind")).lower() != "vehicle":
            continue
        if accepted_only and not _truthy(detection_row.get("reposcan_accepted")):
            continue
        if skip_reviewed and _truthy(detection_row.get("reposcan_reviewed")):
            continue
        confidence = _coerce_float(detection_row.get("confidence"))
        if min_confidence is not None and (confidence is None or confidence < min_confidence):
            continue

        crop_relative_path = _clean_text(detection_row.get("crop_relative_path"))
        crop_path = output_root / Path(crop_relative_path)
        detection_index = _clean_text(detection_row.get("detection_index")) or "0"
        asset_id = _clean_text(detection_row.get("asset_id")) or "unknown_asset"
        top_label, top_confidence = _make_model_top1(detection_row)

        rows.append(
            {
                "crop_id": f"{asset_id}_vehicle_{detection_index}",
                "crop_filepath": str(crop_path.resolve()),
                "source_label": _source_label_from_detection_class(_clean_text(detection_row.get("class_label"))),
                "priority_reason": priority_reason,
                "frame_source_path": _clean_text(detection_row.get("frame_source_path")),
                "frame_relative_path": _clean_text(detection_row.get("frame_relative_path")),
                "metadata_relative_path": _clean_text(detection_row.get("metadata_relative_path")),
                "capture_session_id": _clean_text(detection_row.get("capture_session_id")),
                "timestamp_utc": _clean_text(detection_row.get("timestamp_utc")),
                "bbox_x": _clean_text(detection_row.get("bbox_x")),
                "bbox_y": _clean_text(detection_row.get("bbox_y")),
                "bbox_w": _clean_text(detection_row.get("bbox_w")),
                "bbox_h": _clean_text(detection_row.get("bbox_h")),
                "suggested_vehicle_color": _slugify(detection_row.get("suggested_color")),
                "suggested_vehicle_color_confidence": _clean_text(detection_row.get("suggested_color_confidence")),
                "suggested_vehicle_make": _slugify(detection_row.get("suggested_make")),
                "suggested_vehicle_model": _slugify(detection_row.get("suggested_model")),
                "suggested_make_model_top1": top_label,
                "suggested_make_model_top1_confidence": top_confidence,
                "suggested_vehicle_year": _clean_text(detection_row.get("suggested_year")),
                "suggested_vehicle_year_confidence": _clean_text(detection_row.get("suggested_year_confidence")),
                "vehicle_detector_provider": _clean_text(detection_row.get("vehicle_detector_provider")),
                "attribute_provider": _clean_text(detection_row.get("attribute_provider")),
                "reposcan_accepted": "false",
                "reposcan_reviewed": "false",
                "reposcan_class_label": "",
                "reposcan_vehicle_make": "",
                "reposcan_vehicle_model": "",
                "reposcan_vehicle_year": "",
                "reposcan_vehicle_color": "",
                "reposcan_oklahoma_tags": "",
                "reviewer_notes": "",
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    detection_review_csv = Path(args.detection_review_csv).resolve()
    output_csv = Path(args.output_csv).resolve()
    if output_csv.exists() and not args.overwrite:
        raise FileExistsError(f"output CSV already exists: {output_csv}. Pass --overwrite to replace it.")

    detection_rows, _ = _read_csv(detection_review_csv)
    rows = build_attribute_review_rows(
        detection_rows,
        detection_review_csv=detection_review_csv,
        min_confidence=args.min_confidence,
        accepted_only=args.accepted_only,
        skip_reviewed=args.skip_reviewed,
        priority_reason=args.priority_reason,
    )
    _write_csv(output_csv, rows)
    print(
        json.dumps(
            {
                "detection_review_csv": str(detection_review_csv),
                "output_csv": str(output_csv),
                "rows": len(rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
