"""Materialize a class-subset ImageFolder for a hierarchical re-rank head.

Some canonical classes are easier to discriminate when isolated from the
larger 30-way classifier head. For example, chevrolet_suburban gets confused
with chevrolet_tahoe because both share the same front-end design, but a
small head trained only on (suburban, tahoe, yukon) can use rear-quarter and
length cues that get washed out in the 30-way softmax.

This script reads the canonical make/model manifest, filters to a list of
class labels, and writes a fresh ImageFolder dataset plus a typed manifest
under the vehicle_make_model_classification task tag. Use it to build a
re-rank training corpus for any confusable subset (Chevy full-size SUVs,
Jeep models, etc.).
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
        description="Build a class-subset ImageFolder for a hierarchical re-rank head.",
    )
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument(
        "--keep-classes",
        required=True,
        help="Comma-separated list of canonical class labels to retain.",
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--dataset-name", required=True)
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


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest

    keep_classes = {c.strip() for c in args.keep_classes.split(",") if c.strip()}
    print(f"Filtering to {len(keep_classes)} classes: {sorted(keep_classes)}")

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

    aggregated_assets: list[dict[str, Any]] = []
    label_rows_by_split: dict[str, list[dict[str, Any]]] = {s: [] for s in SPLITS}
    counts_by_class_split: dict[tuple[str, str], int] = defaultdict(int)

    for asset in src.assets:
        split_token = asset.relative_path.split("/", 2)[1] if asset.relative_path.startswith("splits/") else None
        if split_token not in SPLITS:
            continue
        class_label = asset.relative_path.rsplit("/", 2)[1]
        if class_label not in keep_classes:
            continue
        src_file = src_storage_root / asset.relative_path
        if not src_file.exists():
            continue
        file_name = Path(asset.relative_path).name
        unified_relative = f"splits/{split_token}/{class_label}/{file_name}"
        destination = output_root / unified_relative
        _link_or_copy(src_file, destination, args.copy)
        counts_by_class_split[(class_label, split_token)] += 1

        asset_dict = asset.model_dump(mode="json")
        asset_dict["relative_path"] = unified_relative
        asset_dict["tags"] = list(asset.tags) + [
            f"rerank_subset:{args.dataset_name}",
            f"original_class:{class_label}",
        ]
        aggregated_assets.append(asset_dict)
        label_rows_by_split[split_token].append(
            {
                "image_file": f"{class_label}/{file_name}",
                "class_label": class_label,
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
                "tags": ["hierarchical_rerank", "imagefolder"],
            }
        )

    manifest_payload = {
        "dataset_name": args.dataset_name,
        "dataset_version": args.dataset_version,
        "task": "vehicle_make_model_classification",
        "format": "imagefolder",
        "storage_root": str(output_root),
        "review_status": "pending",
        "provenance": {
            "source_name": f"Class-subset rerank from {src.dataset_name}",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": src.provenance.license_name,
            "license_reference": str(source_manifest_path),
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                f"Filtered to {len(keep_classes)} classes from the source manifest "
                "for hierarchical re-rank head training. License and per-image "
                "provenance carry from the source manifest."
            ),
        },
        "annotation_review": None,
        "assets": aggregated_assets,
        "splits": splits_meta,
        "notes": f"Re-rank subset: {sorted(keep_classes)}",
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest_payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )

    summary = {
        "dataset_name": args.dataset_name,
        "manifest_path": str(manifest_path.relative_to(repo_root)),
        "kept_classes": sorted(keep_classes),
        "total_assets": len(aggregated_assets),
        "by_class_split": {
            f"{c}|{s}": n for (c, s), n in sorted(counts_by_class_split.items())
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
