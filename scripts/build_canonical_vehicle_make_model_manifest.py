"""Union multiple canonical-taxonomy vehicle make/model datasets into one
ImageFolder dataset and a single training manifest.

This is path 2 of the post-VMMRdb integration plan: take the v3 EfficientNet-B0
backbone, replace the classifier head, and retrain on the canonical 20-class
taxonomy. The trainer expects one ImageFolder root, so we materialize a
unified folder tree by hard-linking (or copying as fallback) source images
into a fresh `splits/<split>/<class>/` layout while preserving per-image
provenance in `labels.csv` and the union manifest.

Source manifests are read by the existing typed loader so any review_status,
license metadata, and tags carry through.
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
    src = repo_root / "packages" / "contracts" / "src"
    sys.path.insert(0, str(src))


SPLITS = ("train", "validation", "holdout")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Union canonical-taxonomy vehicle make/model datasets into one ImageFolder.",
    )
    parser.add_argument(
        "--source-manifest",
        action="append",
        required=True,
        help="Path to a canonical-taxonomy training-dataset manifest. May be repeated.",
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument(
        "--dataset-name",
        default="canonical-vehicle-make-model-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of hard-linking (use if hard-link target FS does not support it).",
    )
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


def _split_value(split_enum) -> str:
    return split_enum.value if hasattr(split_enum, "value") else str(split_enum)


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
            print(
                f"ERROR: {output_root} is not empty; pass --overwrite to replace it",
                file=sys.stderr,
            )
            return 2
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    aggregated_assets: list[dict[str, Any]] = []
    label_rows_by_split: dict[str, list[dict[str, Any]]] = {s: [] for s in SPLITS}
    class_counts_by_split: dict[str, dict[str, int]] = {s: defaultdict(int) for s in SPLITS}
    sources_summary: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    seen_relative_paths: set[str] = set()

    for source_path in args.source_manifest:
        manifest_input = Path(source_path)
        if not manifest_input.is_absolute():
            manifest_input = (repo_root / manifest_input).resolve()
        manifest = load_training_dataset_manifest(manifest_input)
        source_storage_root = _resolve_storage_root(repo_root, manifest.storage_root)

        per_source = {
            "manifest_path": str(manifest_input.relative_to(repo_root)),
            "dataset_name": manifest.dataset_name,
            "dataset_version": manifest.dataset_version,
            "review_status": manifest.review_status.value,
            "license_name": manifest.provenance.license_name,
            "license_reference": manifest.provenance.license_reference,
            "asset_count": 0,
            "by_split": defaultdict(int),
            "by_class": defaultdict(int),
        }

        for asset in manifest.assets:
            asset_path = asset.relative_path
            split_token = asset_path.split("/", 2)[1] if asset_path.startswith("splits/") else None
            if split_token not in SPLITS:
                continue
            class_label = asset.relative_path.rsplit("/", 2)[1]

            unique_asset_id = f"{manifest.dataset_name}::{asset.asset_id}"
            if unique_asset_id in seen_asset_ids:
                continue
            seen_asset_ids.add(unique_asset_id)

            file_name = Path(asset.relative_path).name
            stem = Path(file_name).stem
            suffix = Path(file_name).suffix
            unified_file_name = f"{manifest.dataset_name}_{stem}{suffix}"
            unified_relative = f"splits/{split_token}/{class_label}/{unified_file_name}"
            if unified_relative in seen_relative_paths:
                continue
            seen_relative_paths.add(unified_relative)

            source_file = source_storage_root / asset.relative_path
            if not source_file.exists():
                print(f"WARNING: missing source file: {source_file}", file=sys.stderr)
                continue
            destination_file = output_root / unified_relative
            _link_or_copy(source_file, destination_file, args.copy)

            tags = list(asset.tags) + [
                f"source_dataset:{manifest.dataset_name}",
                f"source_review_status:{manifest.review_status.value}",
            ]

            asset_dict = asset.model_dump(mode="json")
            asset_dict["asset_id"] = unique_asset_id
            asset_dict["relative_path"] = unified_relative
            asset_dict["tags"] = tags
            aggregated_assets.append(asset_dict)

            label_rows_by_split[split_token].append(
                {
                    "image_file": f"{class_label}/{unified_file_name}",
                    "class_label": class_label,
                    "vehicle_make": asset.vehicle_make or "",
                    "vehicle_model": asset.vehicle_model or "",
                    "vehicle_year": asset.vehicle_year or "",
                    "source_dataset": manifest.dataset_name,
                    "source_asset_id": asset.asset_id,
                    "source_relative_path": asset.relative_path,
                    "license_name": manifest.provenance.license_name or "",
                }
            )
            class_counts_by_split[split_token][class_label] += 1
            per_source["asset_count"] += 1
            per_source["by_split"][split_token] += 1
            per_source["by_class"][class_label] += 1

        per_source["by_split"] = dict(per_source["by_split"])
        per_source["by_class"] = dict(per_source["by_class"])
        sources_summary.append(per_source)

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
                    "source_relative_path",
                    "license_name",
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
                "tags": [
                    "canonical_make_model",
                    "union_of_public_sources",
                    "imagefolder",
                ],
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
            "source_name": "Union of canonical-taxonomy public datasets",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": "Per-image (preserved in labels.csv)",
            "license_reference": "; ".join(
                [s["manifest_path"] for s in sources_summary]
            ),
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                "Materialized union of canonical-taxonomy vehicle make/model "
                "datasets for path-2 head-replacement training. Per-image "
                "license, source dataset name, and original asset id are "
                "preserved in labels.csv and asset tags. Mark as approved "
                "only after a reviewer confirms each constituent dataset's "
                "review_status is acceptable for the intended training run."
            ),
        },
        "annotation_review": None,
        "assets": aggregated_assets,
        "splits": splits_meta,
        "notes": (
            "Canonical 20-class taxonomy (RepoScan Oklahoma-popular targets). "
            "Split balance is inherited from each source manifest; rebalancing "
            "should happen at split-builder level rather than here."
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
        "by_split": {
            split: sum(class_counts_by_split[split].values()) for split in SPLITS
        },
        "by_class": {
            split: dict(sorted(class_counts_by_split[split].items()))
            for split in SPLITS
            if class_counts_by_split[split]
        },
        "sources": sources_summary,
    }
    (output_root / "build_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
