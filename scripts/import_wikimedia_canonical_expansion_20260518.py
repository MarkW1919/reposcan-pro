"""Second-wave Wikimedia bulk importer for canonical-v5 expansion.

Adds 10 new Oklahoma-popular make/model classes on top of the existing
canonical 30 from canonical-v4. Same pattern as the 20260507 expansion
importer — VehicleTargets driven through the rate-limit-resilient
helpers in import_wikimedia_vehicle_dataset.

New classes (10):
  - cadillac_escalade   (full-size luxury SUV, common high-value repos)
  - lincoln_navigator   (Escalade sibling, also common)
  - honda_pilot         (mid-size SUV, popular family vehicle)
  - ford_escape         (compact SUV, high volume)
  - hyundai_elantra     (compact sedan, very common)
  - subaru_outback      (wagon-crossover, popular regionally)
  - kia_sportage        (compact SUV, sibling to Hyundai Tucson)
  - hyundai_santa_fe    (mid-size SUV)
  - chevrolet_malibu    (mid-size sedan, high volume)
  - volkswagen_jetta    (compact sedan, common)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_wikimedia_vehicle_dataset as base


NEW_CLASS_TARGETS: tuple[base.VehicleTarget, ...] = (
    base.VehicleTarget(
        "cadillac_escalade", "cadillac", "escalade", 2010, 2026,
        ("Cadillac Escalade", "Cadillac Escalade ESV", "Cadillac Escalade Platinum"),
        "suv",
        ("Cadillac Escalade (GMT900)", "Cadillac Escalade (GMTK2YL)", "Cadillac Escalade (GMTT1YL)", "Cadillac Escalade"),
    ),
    base.VehicleTarget(
        "lincoln_navigator", "lincoln", "navigator", 2010, 2026,
        ("Lincoln Navigator", "Lincoln Navigator L"),
        "suv",
        ("Lincoln Navigator (third generation)", "Lincoln Navigator (fourth generation)", "Lincoln Navigator"),
    ),
    base.VehicleTarget(
        "honda_pilot", "honda", "pilot", 2010, 2026,
        ("Honda Pilot", "Honda Pilot Elite"),
        "suv",
        ("Honda Pilot (YF3/YF4)", "Honda Pilot (YF5)", "Honda Pilot (YF6)", "Honda Pilot"),
    ),
    base.VehicleTarget(
        "ford_escape", "ford", "escape", 2013, 2026,
        ("Ford Escape", "Ford Kuga"),
        "suv",
        ("Ford Escape (third generation)", "Ford Escape (fourth generation)", "Ford Escape"),
    ),
    base.VehicleTarget(
        "hyundai_elantra", "hyundai", "elantra", 2013, 2026,
        ("Hyundai Elantra", "Hyundai Avante", "Hyundai Elantra GT"),
        "sedan",
        ("Hyundai Elantra (MD)", "Hyundai Elantra (AD)", "Hyundai Elantra (CN7)", "Hyundai Elantra"),
    ),
    base.VehicleTarget(
        "subaru_outback", "subaru", "outback", 2010, 2026,
        ("Subaru Outback", "Subaru Legacy Outback"),
        "suv",
        ("Subaru Outback (BR)", "Subaru Outback (BS)", "Subaru Outback (BT)", "Subaru Outback"),
    ),
    base.VehicleTarget(
        "kia_sportage", "kia", "sportage", 2011, 2026,
        ("Kia Sportage",),
        "suv",
        ("Kia Sportage (SL)", "Kia Sportage (QL)", "Kia Sportage (NQ5)", "Kia Sportage"),
    ),
    base.VehicleTarget(
        "hyundai_santa_fe", "hyundai", "santa_fe", 2013, 2026,
        ("Hyundai Santa Fe", "Hyundai Santa Fe Sport", "Hyundai Maxcruz"),
        "suv",
        ("Hyundai Santa Fe (DM)", "Hyundai Santa Fe (TM)", "Hyundai Santa Fe (MX5)", "Hyundai Santa Fe"),
    ),
    base.VehicleTarget(
        "chevrolet_malibu", "chevrolet", "malibu", 2013, 2024,
        ("Chevrolet Malibu",),
        "sedan",
        ("Chevrolet Malibu (eighth generation)", "Chevrolet Malibu (ninth generation)", "Chevrolet Malibu"),
    ),
    base.VehicleTarget(
        "volkswagen_jetta", "volkswagen", "jetta", 2011, 2026,
        ("Volkswagen Jetta", "Volkswagen Vento", "VW Jetta"),
        "sedan",
        ("Volkswagen Jetta (A6)", "Volkswagen Jetta (A7)", "Volkswagen Jetta"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wikimedia bulk importer for canonical-v5 second-wave expansion (10 new classes)."
    )
    parser.add_argument(
        "--output-root",
        default="data/curated/wikimedia_canonical_expansion_20260518",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/manifests/public/wikimedia-canonical-expansion-20260518.yaml",
    )
    parser.add_argument(
        "--dataset-name",
        default="wikimedia-canonical-expansion-20260518",
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
    parser.add_argument("--sleep-seconds", type=float, default=1.5)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_path)
    base._prepare_output(output_root, manifest_path, args.overwrite)

    all_records: list[dict[str, Any]] = []
    per_target_counts: dict[str, int] = {}
    for target in NEW_CLASS_TARGETS:
        records = base.import_target(target, output_root=output_root, args=args)
        all_records.extend(records)
        per_target_counts[target.class_label] = (
            per_target_counts.get(target.class_label, 0) + len(records)
        )

    split_records = base._split_records(all_records, args)
    base._materialize_splits(output_root, split_records, args.dry_run)
    base._write_manifest(
        output_root=output_root,
        manifest_path=manifest_path,
        args=args,
        split_records=split_records,
    )

    summary: dict[str, Any] = {
        "dataset_name": args.dataset_name,
        "total_samples": len(all_records),
        "classes": dict(sorted(per_target_counts.items())),
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
