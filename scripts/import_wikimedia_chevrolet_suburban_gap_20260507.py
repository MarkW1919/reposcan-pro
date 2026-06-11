"""Gap-fill importer for the chevrolet_suburban class from Wikimedia Commons.

The canonical-v1 model showed 58.3% holdout accuracy on chevrolet_suburban
(7/12, with 5 confused with chevrolet_tahoe). Root cause: only 87 training
samples and a near-identical front-end design with the Tahoe at small scale.
This gap-fill pulls additional clean exterior Suburban images from Wikimedia
Commons subcategories spanning the recent generations (GMTK2YC, GMTT1YC) so
the canonical-v2 retrain can learn the Suburban-specific length and rear-end
cues that distinguish it from the Tahoe.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_wikimedia_vehicle_dataset as base


SUBURBAN_TARGET = base.VehicleTarget(
    class_label="chevrolet_suburban",
    make="chevrolet",
    model="suburban",
    year_start=2010,
    year_end=2026,
    search_names=(
        "Chevrolet Suburban",
        "Chevy Suburban",
        "Chevrolet Suburban LTZ",
        "Chevrolet Suburban Premier",
    ),
    vehicle_class="suv",
    commons_categories=(
        "Chevrolet Suburban (GMTK2YC)",
        "Chevrolet Suburban (GMTT1YC)",
        "Chevrolet Suburban (GMT931)",
        "Chevrolet Suburban (GMT830)",
        "Chevrolet Suburban Z71",
        "Chevrolet Suburban in police service",
        "Chevrolet Suburban",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import chevrolet_suburban exterior images from Wikimedia Commons. "
            "Produces a pending-review dataset with full per-image provenance "
            "for the canonical-v2 Suburban-vs-Tahoe disambiguation work."
        )
    )
    parser.add_argument(
        "--output-root",
        default="data/curated/wikimedia_chevrolet_suburban_gap_20260507",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/manifests/public/wikimedia-chevrolet-suburban-gap-20260507.yaml",
    )
    parser.add_argument(
        "--dataset-name",
        default="wikimedia-chevrolet-suburban-gap-20260507",
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--max-per-class", type=int, default=120)
    parser.add_argument("--search-limit", type=int, default=50)
    parser.add_argument("--thumbnail-width", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--sleep-seconds", type=float, default=1.5)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_path)
    base._prepare_output(output_root, manifest_path, args.overwrite)

    records = base.import_target(SUBURBAN_TARGET, output_root=output_root, args=args)
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
        "classes": {SUBURBAN_TARGET.class_label: len(records)},
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
