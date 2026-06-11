from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PLATE_EXTRA_FIELDS = [
    "priority_group_key",
    "priority_group_size",
    "priority_rank_within_group",
    "priority_reason",
]

VEHICLE_EXTRA_FIELDS = [
    "priority_group_key",
    "priority_group_size",
    "priority_rank_within_group",
    "priority_reason",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build reduced priority review queues from mobile-capture detection and attribute outputs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plate = subparsers.add_parser("plate-ocr", help="Build a priority queue for plate OCR review.")
    plate.add_argument("--input-csv", required=True)
    plate.add_argument("--output-csv", required=True)
    plate.add_argument("--max-per-group", type=int, default=5)
    plate.add_argument("--min-ocr-confidence", type=float)
    plate.add_argument("--overwrite", action="store_true")

    vehicle = subparsers.add_parser("vehicle-attributes", help="Build a priority queue for vehicle attribute review.")
    vehicle.add_argument("--input-csv", required=True)
    vehicle.add_argument("--output-csv", required=True)
    vehicle.add_argument("--max-per-group", type=int, default=5)
    vehicle.add_argument("--min-vlm-confidence", type=float)
    vehicle.add_argument("--prefer-accept-suggestions", action="store_true")
    vehicle.add_argument("--overwrite", action="store_true")

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


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _ensure_fieldnames(fieldnames: list[str], extra_fields: list[str]) -> list[str]:
    result = list(fieldnames)
    for field in extra_fields:
        if field not in result:
            result.append(field)
    return result


def _group_rows(rows: list[dict[str, str]], key_func):
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(key_func(row), []).append(row)
    return grouped


def build_plate_priority_rows(
    rows: list[dict[str, str]],
    *,
    max_per_group: int,
    min_ocr_confidence: float | None,
) -> list[dict[str, str]]:
    filtered = [row for row in rows if _clean_text(row.get("detection_kind")).lower() == "plate"]
    if min_ocr_confidence is not None:
        filtered = [
            row
            for row in filtered
            if _coerce_float(row.get("ocr_confidence"), default=-1.0) >= min_ocr_confidence
        ]

    def key_func(row: dict[str, str]) -> str:
        text = _slugify(row.get("ocr_text"))
        return text or "ocr_unknown"

    grouped = _group_rows(filtered, key_func)
    prioritized: list[dict[str, str]] = []
    for group_key, group_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        ranked = sorted(
            group_rows,
            key=lambda row: (
                -_coerce_float(row.get("ocr_confidence")),
                -_coerce_float(row.get("confidence")),
                _clean_text(row.get("timestamp_utc")),
            ),
        )
        for index, row in enumerate(ranked[: max(max_per_group, 0)], start=1):
            updated = dict(row)
            updated["priority_group_key"] = group_key
            updated["priority_group_size"] = str(len(group_rows))
            updated["priority_rank_within_group"] = str(index)
            updated["priority_reason"] = f"plate_ocr_group:{group_key}"
            prioritized.append(updated)
    return prioritized


def _vehicle_group_key(row: dict[str, str]) -> str:
    make = _slugify(row.get("suggested_vlm_vehicle_make"))
    model = _slugify(row.get("suggested_vlm_vehicle_model_family") or row.get("suggested_vlm_vehicle_model"))
    body_type = _slugify(row.get("suggested_vlm_body_type"))
    source_label = _slugify(row.get("source_label"))
    if make and model:
        return f"{make}_{model}"
    if model:
        return model
    if body_type:
        return f"body_{body_type}"
    return source_label or "vehicle_unknown"


def build_vehicle_priority_rows(
    rows: list[dict[str, str]],
    *,
    max_per_group: int,
    min_vlm_confidence: float | None,
    prefer_accept_suggestions: bool,
) -> list[dict[str, str]]:
    filtered = list(rows)
    if min_vlm_confidence is not None:
        filtered = [
            row
            for row in filtered
            if _coerce_float(row.get("suggested_vlm_confidence"), default=-1.0) >= min_vlm_confidence
        ]

    grouped = _group_rows(filtered, _vehicle_group_key)
    prioritized: list[dict[str, str]] = []
    for group_key, group_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        ranked = sorted(
            group_rows,
            key=lambda row: (
                0
                if prefer_accept_suggestions and _clean_text(row.get("suggested_vlm_review_action")) == "accept_suggestion"
                else 1,
                -_coerce_float(row.get("suggested_vlm_confidence")),
                _clean_text(row.get("timestamp_utc")),
            ),
        )
        for index, row in enumerate(ranked[: max(max_per_group, 0)], start=1):
            updated = dict(row)
            updated["priority_group_key"] = group_key
            updated["priority_group_size"] = str(len(group_rows))
            updated["priority_rank_within_group"] = str(index)
            updated["priority_reason"] = f"vehicle_group:{group_key}"
            prioritized.append(updated)
    return prioritized


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv).resolve()
    output_csv = Path(args.output_csv).resolve()
    if output_csv.exists() and not args.overwrite:
        raise FileExistsError(f"output CSV already exists: {output_csv}. Pass --overwrite to replace it.")

    rows, fieldnames = _read_csv(input_csv)
    if args.command == "plate-ocr":
        prioritized = build_plate_priority_rows(
            rows,
            max_per_group=args.max_per_group,
            min_ocr_confidence=args.min_ocr_confidence,
        )
        fieldnames = _ensure_fieldnames(fieldnames, PLATE_EXTRA_FIELDS)
    elif args.command == "vehicle-attributes":
        prioritized = build_vehicle_priority_rows(
            rows,
            max_per_group=args.max_per_group,
            min_vlm_confidence=args.min_vlm_confidence,
            prefer_accept_suggestions=args.prefer_accept_suggestions,
        )
        fieldnames = _ensure_fieldnames(fieldnames, VEHICLE_EXTRA_FIELDS)
    else:  # pragma: no cover - argparse guards this
        raise ValueError(f"unsupported command: {args.command}")

    _write_csv(output_csv, prioritized, fieldnames)
    print(
        json.dumps(
            {
                "command": args.command,
                "input_csv": str(input_csv),
                "output_csv": str(output_csv),
                "rows": len(prioritized),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
