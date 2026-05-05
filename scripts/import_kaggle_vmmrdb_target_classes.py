"""Selective importer for the Kaggle VMMRdb dataset.

Extracts only the year-folders that map to our priority make/model classes
from the Kaggle VMMRdb zip (CC0-1.0 license per dataset metadata) into a
RepoScan ImageFolder dataset with full per-image provenance.

The full VMMRdb has 9,170 year-specific class folders covering 1950-2016
across 291,752 images. We filter to ~20 priority make/model classes
relevant to RepoScan Pro's Oklahoma-popular vehicle deployment.

Usage:
    python scripts/import_kaggle_vmmrdb_target_classes.py \\
        --zip-path data/raw/kaggle_vmmrdb_full_20260505/vmmrdb-dataset.zip \\
        --output-root data/curated/kaggle_vmmrdb_target_classes_20260505 \\
        --manifest-path data/manifests/public/kaggle-vmmrdb-target-classes-20260505.yaml
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SPLITS = ("train", "validation", "holdout")
KAGGLE_LICENSE_NAME = "CC0-1.0"
KAGGLE_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
KAGGLE_DATASET_URL = "https://www.kaggle.com/datasets/prabashwara/vmmrdb-dataset"


@dataclass(frozen=True)
class ClassMapping:
    class_label: str
    vehicle_make: str
    vehicle_model: str
    vehicle_class: str
    folder_patterns: tuple[str, ...]
    year_min: int = 1995
    year_max: int = 2026


CLASS_MAPPINGS: tuple[ClassMapping, ...] = (
    ClassMapping("ford_f_series", "ford", "f_series", "pickup",
                 (r"^ford_f-?150_(\d{4})$", r"^ford_f-?250_(\d{4})$",
                  r"^ford_f-?350_(\d{4})$", r"^ford_f-?450_(\d{4})$",
                  r"^ford_super_?duty_(\d{4})$"), 2008),
    ClassMapping("chevrolet_silverado", "chevrolet", "silverado", "pickup",
                 (r"^chevrolet_silverado(?:_\d+)?_(\d{4})$",), 2008),
    ClassMapping("chevrolet_tahoe", "chevrolet", "tahoe", "suv",
                 (r"^chevrolet_tahoe_(\d{4})$",), 2008),
    ClassMapping("chevrolet_suburban", "chevrolet", "suburban", "suv",
                 (r"^chevrolet_suburban_(\d{4})$",), 2008),
    ClassMapping("chevrolet_equinox", "chevrolet", "equinox", "suv",
                 (r"^chevrolet_equinox_(\d{4})$",), 2008),
    ClassMapping("ford_expedition", "ford", "expedition", "suv",
                 (r"^ford_expedition_(\d{4})$",), 2008),
    ClassMapping("ford_explorer", "ford", "explorer", "suv",
                 (r"^ford_explorer_(\d{4})$",), 2008),
    ClassMapping("honda_civic", "honda", "civic", "sedan",
                 (r"^honda_civic_(\d{4})$",), 2010),
    ClassMapping("honda_accord", "honda", "accord", "sedan",
                 (r"^honda_accord_(\d{4})$",), 2010),
    ClassMapping("honda_cr_v", "honda", "cr_v", "suv",
                 (r"^honda_cr-?v_(\d{4})$", r"^honda_crv_(\d{4})$"), 2010),
    ClassMapping("nissan_altima", "nissan", "altima", "sedan",
                 (r"^nissan_altima_(\d{4})$",), 2010),
    ClassMapping("nissan_sentra", "nissan", "sentra", "sedan",
                 (r"^nissan_sentra_(\d{4})$",), 2010),
    ClassMapping("nissan_rogue", "nissan", "rogue", "suv",
                 (r"^nissan_rogue_(\d{4})$",), 2010),
    ClassMapping("ram_pickup", "ram", "pickup", "pickup",
                 (r"^dodge_ram_?\d*_(\d{4})$", r"^ram_\d+_(\d{4})$",
                  r"^ram_pickup_(\d{4})$"), 2008),
    ClassMapping("toyota_camry", "toyota", "camry", "sedan",
                 (r"^toyota_camry_(\d{4})$",), 2010),
    ClassMapping("toyota_tacoma", "toyota", "tacoma", "pickup",
                 (r"^toyota_tacoma_(\d{4})$",), 2008),
    ClassMapping("toyota_tundra", "toyota", "tundra", "pickup",
                 (r"^toyota_tundra_(\d{4})$",), 2008),
    ClassMapping("toyota_rav4", "toyota", "rav4", "suv",
                 (r"^toyota_rav-?4_(\d{4})$",), 2008),
    ClassMapping("hyundai_tucson", "hyundai", "tucson", "suv",
                 (r"^hyundai_tucson_(\d{4})$",), 2010),
    ClassMapping("gmc_sierra", "gmc", "sierra", "pickup",
                 (r"^gmc_sierra(?:_\d+)?_(\d{4})$",), 2008),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Selective VMMRdb importer.")
    parser.add_argument("--zip-path", required=True)
    parser.add_argument("--output-root",
                        default="data/curated/kaggle_vmmrdb_target_classes_20260505")
    parser.add_argument("--manifest-path",
                        default="data/manifests/public/kaggle-vmmrdb-target-classes-20260505.yaml")
    parser.add_argument("--dataset-name", default="kaggle-vmmrdb-target-classes-20260505")
    parser.add_argument("--dataset-version",
                        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--max-per-class", type=int, default=400,
                        help="Cap per class to keep balance (0 = uncapped)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan and report counts without extracting")
    return parser.parse_args()


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug_safe(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)


def _classify_folder(folder: str) -> tuple[ClassMapping, int] | None:
    folder_lower = folder.lower()
    for mapping in CLASS_MAPPINGS:
        for pattern in mapping.folder_patterns:
            match = re.match(pattern, folder_lower)
            if match:
                year = int(match.group(1))
                if mapping.year_min <= year <= mapping.year_max:
                    return mapping, year
    return None


def _scan_zip(zip_path: Path) -> dict[str, list[tuple[str, ClassMapping, int]]]:
    """Returns mapping of class_label -> list of (zip_member_name, mapping, year)."""
    by_class: dict[str, list[tuple[str, ClassMapping, int]]] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            parts = name.split("/")
            if len(parts) < 2:
                continue
            folder = parts[-2]
            classified = _classify_folder(folder)
            if classified is None:
                continue
            mapping, year = classified
            by_class.setdefault(mapping.class_label, []).append((name, mapping, year))
    return by_class


def _split_records(
    records: list[dict[str, Any]],
    train_ratio: float,
    validation_ratio: float,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["class_label"], []).append(record)
    result: dict[str, list[dict[str, Any]]] = {split: [] for split in SPLITS}
    for class_records in grouped.values():
        rng.shuffle(class_records)
        count = len(class_records)
        train_count = int(count * train_ratio)
        validation_count = int(count * validation_ratio)
        if count >= 3:
            train_count = max(1, train_count)
            validation_count = max(1, validation_count)
            holdout_count = max(1, count - train_count - validation_count)
            while train_count + validation_count + holdout_count > count:
                train_count -= 1
        else:
            validation_count = 0
            holdout_count = 0
        result["train"].extend(class_records[:train_count])
        result["validation"].extend(class_records[train_count:train_count + validation_count])
        result["holdout"].extend(class_records[train_count + validation_count:])
    return result


def _write_labels_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "image_file", "class_label", "vehicle_make", "vehicle_model",
        "vehicle_year", "source_url", "license_name", "license_url",
        "original_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _write_manifest(
    *,
    output_root: Path,
    manifest_path: Path,
    dataset_name: str,
    dataset_version: str,
    split_records: dict[str, list[dict[str, Any]]],
) -> None:
    assets: list[dict[str, Any]] = []
    for split_name, rows in split_records.items():
        for row in rows:
            assets.append({
                "asset_id": row["asset_id"],
                "relative_path": row["relative_path"],
                "capture_session_id": f"{dataset_name}_{split_name}",
                "timestamp_utc": None,
                "lighting_conditions": ["unknown"],
                "distance_band": None,
                "annotations": ["vehicle_make", "vehicle_model"],
                "tags": [
                    "kaggle_vmmrdb",
                    f"make_model:{row['class_label']}",
                    f"vehicle_class:{row['vehicle_class']}",
                    f"vmmrdb_folder:{row['original_folder']}",
                    f"vehicle_year:{row['vehicle_year']}",
                ],
                "expected_plate_text": None,
                "vehicle_color": None,
                "vehicle_make": row["vehicle_make"],
                "vehicle_model": row["vehicle_model"],
                "vehicle_year": str(row["vehicle_year"]),
                "field_eval_candidate": False,
            })

    manifest = {
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "task": "vehicle_make_model_classification",
        "format": "imagefolder",
        "storage_root": str(output_root.resolve()),
        "review_status": "pending",
        "provenance": {
            "source_name": "Kaggle VMMRdb (prabashwara mirror)",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": KAGGLE_LICENSE_NAME,
            "license_reference": KAGGLE_DATASET_URL,
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                "Filtered to priority make/model classes from the Kaggle VMMRdb "
                "mirror (CC0-1.0). Dataset description: Tafazzoli et al., CVPR 2017 "
                "workshop. Per-image source URL is the Kaggle dataset page; original "
                "VMMRdb path is preserved in tags and labels.csv for review traceability."
            ),
        },
        "annotation_review": None,
        "assets": assets,
        "splits": [
            {
                "split": split_name,
                "relative_path": f"splits/{split_name}",
                "label_path": f"splits/{split_name}/labels.csv",
                "sample_count": len(rows),
                "capture_session_ids": [f"{dataset_name}_{split_name}"],
                "tags": ["kaggle_vmmrdb", "priority_vehicle_make_model",
                         "pending_visual_review"],
            }
            for split_name, rows in split_records.items()
        ],
        "notes": (
            "VMMRdb selective import filtered to 20 priority make/model classes "
            "matching RepoScan Oklahoma-popular vehicle targets. Pending visual "
            "review before promotion. Year range 2008-2016 dominates given the "
            "VMMRdb cutoff at 2016."
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _prepare_output(output_root: Path, manifest_path: Path, overwrite: bool) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"{output_root} is not empty; pass --overwrite to replace it"
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    zip_path = Path(args.zip_path)
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_path)

    if not zip_path.exists():
        print(f"ERROR: zip not found: {zip_path}", file=sys.stderr)
        return 2

    print(f"Scanning {zip_path} ({zip_path.stat().st_size / (1024**3):.2f} GiB)...")
    by_class = _scan_zip(zip_path)
    print("Class scan summary:")
    total_candidates = 0
    for label, items in sorted(by_class.items()):
        print(f"  {label}: {len(items)} candidate images")
        total_candidates += len(items)
    print(f"  TOTAL: {total_candidates}")

    if args.dry_run:
        return 0

    _prepare_output(output_root, manifest_path, args.overwrite)

    rng = random.Random(args.seed)
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as archive:
        for label, items in sorted(by_class.items()):
            if args.max_per_class > 0 and len(items) > args.max_per_class:
                rng.shuffle(items)
                items = items[: args.max_per_class]
            for member_name, mapping, year in items:
                folder = member_name.rsplit("/", 1)[0].rsplit("/", 1)[-1]
                base_name = member_name.rsplit("/", 1)[-1]
                digest = hashlib.sha256(member_name.encode("utf-8")).hexdigest()[:16]
                file_name = f"{label}_{digest}{Path(base_name).suffix.lower()}"
                staging_path = output_root / "_extracted" / label / file_name
                staging_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member_name) as src, open(staging_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                records.append({
                    "asset_id": f"vmmrdb_{label}_{digest}",
                    "class_label": label,
                    "vehicle_make": mapping.vehicle_make,
                    "vehicle_model": mapping.vehicle_model,
                    "vehicle_class": mapping.vehicle_class,
                    "vehicle_year": year,
                    "image_file": file_name,
                    "downloaded_path": str(staging_path),
                    "original_folder": folder,
                    "original_path": member_name,
                    "source_url": KAGGLE_DATASET_URL,
                    "license_name": KAGGLE_LICENSE_NAME,
                    "license_url": KAGGLE_LICENSE_URL,
                })
            print(f"  extracted {label}: {sum(1 for r in records if r['class_label'] == label)} files")

    split_records = _split_records(
        records, args.train_ratio, args.validation_ratio, args.seed,
    )

    for split_name, rows in split_records.items():
        for row in rows:
            relative_path = (
                f"splits/{split_name}/{row['class_label']}/{row['image_file']}"
            )
            destination = output_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(row["downloaded_path"], destination)
            row["relative_path"] = relative_path
            row["image_file"] = f"{row['class_label']}/{row['image_file']}"
        _write_labels_csv(output_root / "splits" / split_name / "labels.csv", rows)
    shutil.rmtree(output_root / "_extracted", ignore_errors=True)

    _write_manifest(
        output_root=output_root,
        manifest_path=manifest_path,
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        split_records=split_records,
    )

    summary = {
        "dataset_name": args.dataset_name,
        "total_samples": len(records),
        "classes": {
            label: sum(1 for r in records if r["class_label"] == label)
            for label in sorted({r["class_label"] for r in records})
        },
        "splits": {split: len(rows) for split, rows in split_records.items()},
        "manifest_path": str(manifest_path),
    }
    (output_root / "import_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
