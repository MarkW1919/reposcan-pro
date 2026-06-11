"""Re-organize the canonical make/model dataset into year-bucket classes.

The canonical-v1/v2/v3 datasets carry vehicle_year metadata per asset
(extracted from VMMRdb folder names and Wikimedia titles). This script
materializes a separate ImageFolder where the classes are year buckets
instead of make/model labels, so we can train a year-aware classifier
head on the same backbone without touching the canonical sources.

Buckets (5):
- bucket_pre_2010   : year <  2011
- bucket_2011_2014  : 2011 <= year <= 2014
- bucket_2015_2018  : 2015 <= year <= 2018
- bucket_2019_2022  : 2019 <= year <= 2022
- bucket_2023_plus  : year >= 2023

Assets that have no usable year are skipped (not labeled "unknown") so
the trained head learns clean bucket boundaries rather than a noisy
catch-all class.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _configure_pythonpath(repo_root: Path) -> None:
    sys.path.insert(0, str(repo_root / "packages" / "contracts" / "src"))


SPLITS = ("train", "validation", "holdout")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a year-bucket ImageFolder dataset from a canonical manifest."
    )
    parser.add_argument(
        "--source-manifest",
        action="append",
        required=True,
        help="Path to a canonical make/model manifest. May be repeated.",
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument(
        "--dataset-name",
        default="canonical-vehicle-year-bucket-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_storage_root(repo_root: Path, storage_root: str) -> Path:
    root = Path(storage_root)
    if root.is_absolute():
        return root
    return (repo_root / root).resolve()


def _link_or_copy(source: Path, destination: Path, copy: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    if copy:
        shutil.copy2(source, destination)
        return
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _bucket_for_year(year: int | None) -> str | None:
    if year is None:
        return None
    if year < 2011:
        return "bucket_pre_2010"
    if year <= 2014:
        return "bucket_2011_2014"
    if year <= 2018:
        return "bucket_2015_2018"
    if year <= 2022:
        return "bucket_2019_2022"
    return "bucket_2023_plus"


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if not value or not value.isdigit():
        return None
    year = int(value)
    if year < 1980 or year > 2030:
        return None
    return year


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = (repo_root / output_root).resolve()
    manifest_path = Path(args.manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()

    if output_root.exists() and any(output_root.iterdir()):
        if not args.overwrite:
            print(f"ERROR: {output_root} not empty; pass --overwrite", file=sys.stderr)
            return 2
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    aggregated_assets: list[dict[str, Any]] = []
    label_rows_by_split: dict[str, list[dict[str, Any]]] = {s: [] for s in SPLITS}
    counts_by_bucket_split: dict[tuple[str, str], int] = defaultdict(int)
    skipped_no_year = 0
    seen_relative_paths: set[str] = set()
    seen_asset_ids: set[str] = set()

    for source_path in args.source_manifest:
        manifest_input = Path(source_path)
        if not manifest_input.is_absolute():
            manifest_input = (repo_root / manifest_input).resolve()
        manifest = load_training_dataset_manifest(manifest_input)
        source_storage_root = _resolve_storage_root(repo_root, manifest.storage_root)

        for asset in manifest.assets:
            split_token = (
                asset.relative_path.split("/", 2)[1]
                if asset.relative_path.startswith("splits/")
                else None
            )
            if split_token not in SPLITS:
                continue
            year = _parse_year(asset.vehicle_year)
            bucket = _bucket_for_year(year)
            if bucket is None:
                skipped_no_year += 1
                continue

            unique_asset_id = f"{manifest.dataset_name}::{asset.asset_id}"
            if unique_asset_id in seen_asset_ids:
                continue
            seen_asset_ids.add(unique_asset_id)

            file_name = Path(asset.relative_path).name
            stem = Path(file_name).stem
            suffix = Path(file_name).suffix
            unified_file_name = f"{manifest.dataset_name}_{stem}{suffix}"
            unified_relative = f"splits/{split_token}/{bucket}/{unified_file_name}"
            if unified_relative in seen_relative_paths:
                continue
            seen_relative_paths.add(unified_relative)

            source_file = source_storage_root / asset.relative_path
            if not source_file.exists():
                continue
            destination_file = output_root / unified_relative
            _link_or_copy(source_file, destination_file, args.copy)

            counts_by_bucket_split[(bucket, split_token)] += 1

            asset_dict = asset.model_dump(mode="json")
            asset_dict["asset_id"] = unique_asset_id
            asset_dict["relative_path"] = unified_relative
            asset_dict["tags"] = list(asset.tags) + [
                f"year_bucket:{bucket}",
                f"source_dataset:{manifest.dataset_name}",
            ]
            aggregated_assets.append(asset_dict)

            label_rows_by_split[split_token].append(
                {
                    "image_file": f"{bucket}/{unified_file_name}",
                    "class_label": bucket,
                    "vehicle_make": asset.vehicle_make or "",
                    "vehicle_model": asset.vehicle_model or "",
                    "vehicle_year": str(year),
                    "source_dataset": manifest.dataset_name,
                    "source_asset_id": asset.asset_id,
                }
            )

    for split_name, rows in label_rows_by_split.items():
        if not rows:
            continue
        labels_path = output_root / "splits" / split_name / "labels.csv"
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        with labels_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "image_file",
                    "class_label",
                    "vehicle_make",
                    "vehicle_model",
                    "vehicle_year",
                    "source_dataset",
                    "source_asset_id",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    splits_meta: list[dict[str, Any]] = []
    for split_name in SPLITS:
        rows = label_rows_by_split[split_name]
        if not rows:
            continue
        splits_meta.append(
            {
                "split": split_name,
                "relative_path": f"splits/{split_name}",
                "label_path": f"splits/{split_name}/labels.csv",
                "sample_count": len(rows),
                "capture_session_ids": [f"{args.dataset_name}_{split_name}"],
                "tags": ["canonical_year_bucket", "imagefolder"],
            }
        )

    manifest_payload = {
        "dataset_name": args.dataset_name,
        "dataset_version": args.dataset_version,
        "task": "vehicle_year_classification",
        "format": "imagefolder",
        "storage_root": str(output_root),
        "review_status": "pending",
        "provenance": {
            "source_name": "Reorganized canonical make/model sources by year bucket",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": "Per-image (preserved in source manifests)",
            "license_reference": "; ".join(args.source_manifest),
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                "Year-bucket reorganization of the canonical make/model dataset. "
                "Five buckets: pre_2010, 2011_2014, 2015_2018, 2019_2022, 2023_plus. "
                "Assets without parseable year metadata are excluded so the model "
                "learns clean bucket boundaries."
            ),
        },
        "annotation_review": None,
        "assets": aggregated_assets,
        "splits": splits_meta,
        "notes": (
            f"Skipped {skipped_no_year} assets that lacked usable vehicle_year metadata."
        ),
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest_payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )

    summary = {
        "dataset_name": args.dataset_name,
        "manifest_path": str(manifest_path.relative_to(repo_root)),
        "storage_root": str(output_root.relative_to(repo_root) if output_root.is_relative_to(repo_root) else output_root),
        "skipped_no_year": skipped_no_year,
        "total_assets": len(aggregated_assets),
        "by_bucket_split": {
            f"{bucket}|{split}": count
            for (bucket, split), count in sorted(counts_by_bucket_split.items())
        },
    }
    (output_root / "build_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
