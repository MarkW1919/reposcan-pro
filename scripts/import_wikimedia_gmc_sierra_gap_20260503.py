"""Gap-fill importer for the gmc_sierra class from Wikimedia Commons.

The existing NHTSA Oklahoma popular dataset only has ~10 GMC Sierra training
images, which is insufficient to train a make/model classifier. This script
reuses the helpers from import_wikimedia_vehicle_dataset.py to pull
license-clean, rights-aware GMC Sierra exterior images from Wikimedia Commons
into a separate, pending-review dataset (does not overwrite existing data).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_wikimedia_vehicle_dataset as base


GMC_SIERRA_TARGET = base.VehicleTarget(
    class_label="gmc_sierra",
    make="gmc",
    model="sierra",
    year_start=2008,
    year_end=2026,
    search_names=("GMC Sierra", "GMC Sierra 1500", "GMC Sierra Denali", "GMC Sierra 2500"),
    vehicle_class="pickup",
    commons_categories=(
        "GMC Sierra (GMTK2XX)",
        "GMC Sierra (GMTT1XX)",
        "GMC Sierra (GMT902/GMT912)",
        "GMC Sierra Denali",
        "GMC Sierra 1500",
        "GMC Sierra 2500",
        "GMC Sierra 3500",
        "GMC Sierra pickups",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import gmc_sierra exterior images from Wikimedia Commons. "
            "Produces a pending-review dataset with full per-image provenance."
        )
    )
    parser.add_argument(
        "--output-root",
        default="data/curated/wikimedia_gmc_sierra_gap_20260503",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/manifests/public/wikimedia-gmc-sierra-gap-20260503.yaml",
    )
    parser.add_argument(
        "--dataset-name",
        default="wikimedia-gmc-sierra-gap-20260503",
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--max-per-class", type=int, default=80)
    parser.add_argument("--search-limit", type=int, default=50)
    parser.add_argument("--thumbnail-width", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--sleep-seconds", type=float, default=1.2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_path)
    base._prepare_output(output_root, manifest_path, args.overwrite)

    records = base.import_target(GMC_SIERRA_TARGET, output_root=output_root, args=args)
    split_records = base._split_records(records, args)
    base._materialize_splits(output_root, split_records, args.dry_run)
    base._write_manifest(
        output_root=output_root,
        manifest_path=manifest_path,
        args=args,
        split_records=split_records,
    )

    summary: dict[str, Any] = {
        "dataset_name": args.dataset_name,
        "total_samples": len(records),
        "classes": {GMC_SIERRA_TARGET.class_label: len(records)},
        "splits": {split: len(rows) for split, rows in split_records.items()},
        "manifest_path": str(manifest_path),
    }
    (output_root / "import_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
