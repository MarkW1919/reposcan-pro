"""Bulk Wikimedia Commons importer for canonical-taxonomy expansion.

This script extends the canonical 20-class vehicle make/model dataset with:
1. Additional Oklahoma-popular classes (Jeep Grand Cherokee, GMC Yukon,
   Dodge Charger, Toyota Corolla, etc.) so the model handles a wider range
   of repossession-relevant vehicles.
2. Modern-generation year gap-fills (2017+) for existing classes whose
   VMMRdb-sourced data only covers 2008-2016.

Both flows reuse the rate-limit-resilient downloader from
import_wikimedia_vehicle_dataset.py and write a single dataset/manifest pair
that can be unioned with the existing canonical sources.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_wikimedia_vehicle_dataset as base


# New canonical classes spanning the most common Oklahoma repossession vehicles
# that are absent from the existing 20-class taxonomy.
NEW_CLASS_TARGETS: tuple[base.VehicleTarget, ...] = (
    base.VehicleTarget(
        "jeep_grand_cherokee", "jeep", "grand_cherokee", 2014, 2026,
        ("Jeep Grand Cherokee", "Jeep Grand Cherokee Limited"),
        "suv",
        ("Jeep Grand Cherokee (WK2)", "Jeep Grand Cherokee (WL)"),
    ),
    base.VehicleTarget(
        "jeep_wrangler", "jeep", "wrangler", 2010, 2026,
        ("Jeep Wrangler", "Jeep Wrangler Unlimited"),
        "suv",
        ("Jeep Wrangler (JK)", "Jeep Wrangler (JL)"),
    ),
    base.VehicleTarget(
        "gmc_yukon", "gmc", "yukon", 2010, 2026,
        ("GMC Yukon", "GMC Yukon Denali", "GMC Yukon XL"),
        "suv",
        ("GMC Yukon (GMT900)", "GMC Yukon (GMTK2YC)", "GMC Yukon (GMTT1YC)"),
    ),
    base.VehicleTarget(
        "dodge_charger", "dodge", "charger", 2011, 2023,
        ("Dodge Charger", "Dodge Charger SXT", "Dodge Charger R/T"),
        "sedan",
        ("Dodge Charger (LD)",),
    ),
    base.VehicleTarget(
        "dodge_durango", "dodge", "durango", 2011, 2026,
        ("Dodge Durango",),
        "suv",
        ("Dodge Durango (WD)",),
    ),
    base.VehicleTarget(
        "toyota_corolla", "toyota", "corolla", 2014, 2026,
        ("Toyota Corolla", "Toyota Corolla LE", "Toyota Corolla SE"),
        "sedan",
        ("Toyota Corolla (E170)", "Toyota Corolla (E210)"),
    ),
    base.VehicleTarget(
        "toyota_highlander", "toyota", "highlander", 2014, 2026,
        ("Toyota Highlander", "Toyota Highlander Limited"),
        "suv",
        ("Toyota Highlander (XU50)", "Toyota Highlander (XU70)"),
    ),
    base.VehicleTarget(
        "toyota_4runner", "toyota", "4runner", 2010, 2026,
        ("Toyota 4Runner", "Toyota 4Runner TRD"),
        "suv",
        ("Toyota 4Runner (N280)",),
    ),
    base.VehicleTarget(
        "hyundai_sonata", "hyundai", "sonata", 2014, 2026,
        ("Hyundai Sonata",),
        "sedan",
        ("Hyundai Sonata (LF)", "Hyundai Sonata (DN8)"),
    ),
    base.VehicleTarget(
        "kia_sorento", "kia", "sorento", 2014, 2026,
        ("Kia Sorento",),
        "suv",
        ("Kia Sorento (UM)", "Kia Sorento (MQ4)"),
    ),
)


# Modern-generation gap-fills for existing canonical classes.
# These pull 2017+ images via Wikimedia subcategories that VMMRdb does not cover.
MODERN_YEAR_TARGETS: tuple[base.VehicleTarget, ...] = (
    base.VehicleTarget(
        "ford_f_series", "ford", "f_series", 2017, 2026,
        ("Ford F-150", "Ford F-250", "Ford Super Duty"),
        "pickup",
        ("Ford F-150 (fourteenth generation)", "Ford F-Series (Super Duty fourth generation)"),
    ),
    base.VehicleTarget(
        "chevrolet_silverado", "chevrolet", "silverado", 2017, 2026,
        ("Chevrolet Silverado",),
        "pickup",
        ("Chevrolet Silverado (GMTT1XX)",),
    ),
    base.VehicleTarget(
        "ram_pickup", "ram", "pickup", 2017, 2026,
        ("Ram 1500", "Ram 2500"),
        "pickup",
        ("Ram 1500 (DT)",),
    ),
    base.VehicleTarget(
        "toyota_camry", "toyota", "camry", 2017, 2026,
        ("Toyota Camry",),
        "sedan",
        ("Toyota Camry (XV70)", "Toyota Camry (XV80)"),
    ),
    base.VehicleTarget(
        "honda_civic", "honda", "civic", 2017, 2026,
        ("Honda Civic",),
        "sedan",
        ("Honda Civic (tenth generation)", "Honda Civic (eleventh generation)"),
    ),
    base.VehicleTarget(
        "honda_accord", "honda", "accord", 2017, 2026,
        ("Honda Accord",),
        "sedan",
        ("Honda Accord (tenth generation)", "Honda Accord (eleventh generation)"),
    ),
    base.VehicleTarget(
        "nissan_altima", "nissan", "altima", 2019, 2026,
        ("Nissan Altima",),
        "sedan",
        ("Nissan Altima (L34)",),
    ),
    base.VehicleTarget(
        "nissan_sentra", "nissan", "sentra", 2020, 2026,
        ("Nissan Sentra",),
        "sedan",
        ("Nissan Sentra (B18)",),
    ),
    base.VehicleTarget(
        "nissan_rogue", "nissan", "rogue", 2017, 2026,
        ("Nissan Rogue",),
        "suv",
        ("Nissan Rogue (T32)", "Nissan Rogue (T33)"),
    ),
    base.VehicleTarget(
        "hyundai_tucson", "hyundai", "tucson", 2017, 2026,
        ("Hyundai Tucson",),
        "suv",
        ("Hyundai Tucson (TL)", "Hyundai Tucson (NX4)"),
    ),
    base.VehicleTarget(
        "honda_cr_v", "honda", "cr_v", 2017, 2026,
        ("Honda CR-V",),
        "suv",
        ("Honda CR-V (RM)", "Honda CR-V (RW)", "Honda CR-V (RS)"),
    ),
    base.VehicleTarget(
        "toyota_rav4", "toyota", "rav4", 2017, 2026,
        ("Toyota RAV4",),
        "suv",
        ("Toyota RAV4 (XA40)", "Toyota RAV4 (XA50)"),
    ),
    base.VehicleTarget(
        "ford_explorer", "ford", "explorer", 2020, 2026,
        ("Ford Explorer",),
        "suv",
        ("Ford Explorer (sixth generation)",),
    ),
    base.VehicleTarget(
        "chevrolet_tahoe", "chevrolet", "tahoe", 2017, 2026,
        ("Chevrolet Tahoe",),
        "suv",
        ("Chevrolet Tahoe (GMTK2YC)", "Chevrolet Tahoe (GMTT1YC)"),
    ),
    base.VehicleTarget(
        "chevrolet_equinox", "chevrolet", "equinox", 2018, 2026,
        ("Chevrolet Equinox",),
        "suv",
        ("Chevrolet Equinox (third generation)",),
    ),
    base.VehicleTarget(
        "ford_expedition", "ford", "expedition", 2018, 2026,
        ("Ford Expedition",),
        "suv",
        ("Ford Expedition (fourth generation)",),
    ),
    base.VehicleTarget(
        "toyota_tacoma", "toyota", "tacoma", 2017, 2026,
        ("Toyota Tacoma",),
        "pickup",
        ("Toyota Tacoma (third generation)",),
    ),
    base.VehicleTarget(
        "toyota_tundra", "toyota", "tundra", 2017, 2026,
        ("Toyota Tundra",),
        "pickup",
        ("Toyota Tundra (XK50)", "Toyota Tundra (XK70)"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk Wikimedia importer for canonical taxonomy expansion."
    )
    parser.add_argument("--mode", choices=("new_classes", "modern_years", "all"), default="all")
    parser.add_argument(
        "--output-root",
        default="data/curated/wikimedia_canonical_expansion_20260507",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/manifests/public/wikimedia-canonical-expansion-20260507.yaml",
    )
    parser.add_argument(
        "--dataset-name",
        default="wikimedia-canonical-expansion-20260507",
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

    targets: list[base.VehicleTarget] = []
    if args.mode in ("new_classes", "all"):
        targets.extend(NEW_CLASS_TARGETS)
    if args.mode in ("modern_years", "all"):
        targets.extend(MODERN_YEAR_TARGETS)

    all_records: list[dict[str, Any]] = []
    per_target_counts: dict[str, int] = {}
    for target in targets:
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
        "mode": args.mode,
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
