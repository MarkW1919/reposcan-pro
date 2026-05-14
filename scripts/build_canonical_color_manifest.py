"""Re-organize Synset-Boulevard supplemental images by color_category and emit
a typed manifest for vehicle_color_classification training.

The Synset-Boulevard importer already wrote per-image color labels into the
asset metadata (color_labels.csv plus the manifest tags). This script reads
the synset-boulevard-canonical-supplemental manifest, groups assets by their
color_category value, and materializes an ImageFolder dataset where each
class directory is a color name (e.g., splits/train/red/<image>.jpg).

Per ADR-029, synthetic-only data lands in train split only. We carve a small
deterministic validation split (~12%) from the same source for sanity-check
metrics; a real-data color holdout has to come from a separate pipeline
later because the canonical real-image dataset does not have color labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _configure_pythonpath(repo_root: Path) -> None:
    sys.path.insert(0, str(repo_root / "packages" / "contracts" / "src"))


VALIDATION_RATIO = 0.12
SPLITS = ("train", "validation")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize a color-classification ImageFolder from Synset-Boulevard supplemental.",
    )
    parser.add_argument(
        "--source-manifest",
        default="data/manifests/public/synset-boulevard-canonical-supplemental-20260509.yaml",
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument(
        "--dataset-name",
        default="canonical-vehicle-color-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--seed", type=int, default=42)
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

    source_manifest_path = Path(args.source_manifest)
    if not source_manifest_path.is_absolute():
        source_manifest_path = (repo_root / source_manifest_path).resolve()
    src = load_training_dataset_manifest(source_manifest_path)
    src_storage_root = _resolve_storage_root(repo_root, src.storage_root)

    # Group assets by color
    assets_by_color: dict[str, list[Any]] = defaultdict(list)
    skipped_no_color = 0
    for asset in src.assets:
        color = (asset.vehicle_color or "").strip().lower()
        if not color:
            skipped_no_color += 1
            continue
        assets_by_color[color].append(asset)

    print(f"Loaded {len(src.assets)} source assets, skipped {skipped_no_color} with no color")
    print(f"Found {len(assets_by_color)} color classes")
    for color, items in sorted(assets_by_color.items()):
        print(f"  {color:10}: {len(items):>4} images")

    # Deterministic per-class train/validation split
    rng = random.Random(args.seed)
    split_records: dict[str, list[dict[str, Any]]] = {s: [] for s in SPLITS}
    aggregated_assets: list[dict[str, Any]] = []
    label_rows_by_split: dict[str, list[dict[str, Any]]] = {s: [] for s in SPLITS}
    counts_by_color_split: dict[tuple[str, str], int] = defaultdict(int)

    for color in sorted(assets_by_color):
        items = list(assets_by_color[color])
        rng.shuffle(items)
        n = len(items)
        n_val = max(1, int(n * VALIDATION_RATIO)) if n >= 8 else 0
        n_train = n - n_val
        for idx, asset in enumerate(items):
            split = "validation" if idx >= n_train else "train"
            src_file = src_storage_root / asset.relative_path
            if not src_file.exists():
                continue
            file_name = Path(asset.relative_path).name
            unified_relative = f"splits/{split}/{color}/{file_name}"
            destination = output_root / unified_relative
            _link_or_copy(src_file, destination, args.copy)
            counts_by_color_split[(color, split)] += 1

            asset_dict = asset.model_dump(mode="json")
            asset_dict["relative_path"] = unified_relative
            asset_dict["tags"] = list(asset.tags) + [
                f"color:{color}",
                f"reorganized_from:{src.dataset_name}",
            ]
            aggregated_assets.append(asset_dict)
            label_rows_by_split[split].append(
                {
                    "image_file": f"{color}/{file_name}",
                    "class_label": color,
                    "vehicle_make": asset.vehicle_make or "",
                    "vehicle_model": asset.vehicle_model or "",
                    "vehicle_year": asset.vehicle_year or "",
                    "source_dataset": src.dataset_name,
                    "source_asset_id": asset.asset_id,
                }
            )

    for split, rows in label_rows_by_split.items():
        if not rows:
            continue
        labels_path = output_root / "splits" / split / "labels.csv"
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        with labels_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "image_file", "class_label", "vehicle_make", "vehicle_model",
                    "vehicle_year", "source_dataset", "source_asset_id",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    splits_meta = []
    for split in SPLITS:
        rows = label_rows_by_split[split]
        if not rows:
            continue
        splits_meta.append(
            {
                "split": split,
                "relative_path": f"splits/{split}",
                "label_path": f"splits/{split}/labels.csv",
                "sample_count": len(rows),
                "capture_session_ids": [f"{args.dataset_name}_{split}"],
                "tags": ["canonical_vehicle_color", "synset_boulevard_reorg", "imagefolder"],
            }
        )

    manifest_payload = {
        "dataset_name": args.dataset_name,
        "dataset_version": args.dataset_version,
        "task": "vehicle_color_classification",
        "format": "imagefolder",
        "storage_root": str(output_root),
        "review_status": "pending",
        "provenance": {
            "source_name": "FraunhoferIOSB/Synset-Boulevard color_category, reorganized",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": "CC-BY-4.0",
            "license_reference": "https://huggingface.co/datasets/FraunhoferIOSB/Synset-Boulevard",
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                "Color-classification reorganization of the Synset-Boulevard "
                "synthetic supplemental. 8-class color taxonomy matches "
                "Synset-Boulevard color_category values. All synthetic; a real-image "
                "color holdout has to come from a future field labeling pipeline. "
                "ADR-029 train-only policy is observed because no real validation data "
                "exists yet for color."
            ),
        },
        "annotation_review": None,
        "assets": aggregated_assets,
        "splits": splits_meta,
        "notes": (
            "Color head training corpus. The validation split here is a "
            "deterministic carve-out from the same synthetic source rather "
            "than real-data validation, so accept the resulting head as "
            "review_status: pending until real-data color holdout exists."
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
        "total_assets": len(aggregated_assets),
        "skipped_no_color": skipped_no_color,
        "by_color_split": {
            f"{c}|{s}": n for (c, s), n in sorted(counts_by_color_split.items())
        },
    }
    (output_root / "build_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
