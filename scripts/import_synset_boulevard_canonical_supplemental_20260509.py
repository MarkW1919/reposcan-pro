"""Import the FraunhoferIOSB/Synset-Boulevard synthetic vehicle dataset, filtered
to the canonical 30 make/model classes used by RepoScan Pro.

Synset-Boulevard is a CC-BY-4.0 synthetic VMMR dataset (Fraunhofer IOSB) with
clean per-vehicle attributes including make, model, model_year, color_category,
daytime, and contrast. We use the Bayer_good subset (cleanest realistic
rendering) to supplement the canonical real-image dataset, particularly for
underrepresented classes whose real-data sample counts are below 200.

Per ADR-029, synthetic data only enters the training split, never validation
or holdout. This script enforces that by writing 100% of accepted samples into
splits/train/<class>/.

Outputs:
- data/curated/synset_boulevard_canonical_supplemental_<date>/splits/train/<class>/...
- data/manifests/public/synset-boulevard-canonical-supplemental-<date>.yaml
- color_labels.csv with per-image color_category for downstream color-head training
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SYNSET_LICENSE_NAME = "CC-BY-4.0"
SYNSET_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SYNSET_DATASET_URL = "https://huggingface.co/datasets/FraunhoferIOSB/Synset-Boulevard"


# Canonical class mapping. Each entry is (canonical_label, make_pattern, model_substrings, vehicle_class).
# make_pattern is a case-insensitive exact match on Synset-Boulevard make field.
# model_substrings are case-insensitive substrings; ANY substring matching the model field
# qualifies the record. Order matters within a make: more specific first.
CLASS_MAPPINGS = [
    # Pickups
    ("ford_f_series", "ford", ["f-150", "f-250", "f-350", "f-450", "f150", "f250", "f350", "super duty", "f-series"], "pickup"),
    ("chevrolet_silverado", "chevrolet", ["silverado"], "pickup"),
    ("ram_pickup", "ram", ["1500", "2500", "3500", "ram"], "pickup"),
    ("ram_pickup", "dodge", ["ram"], "pickup"),
    ("gmc_sierra", "gmc", ["sierra"], "pickup"),
    ("toyota_tacoma", "toyota", ["tacoma"], "pickup"),
    ("toyota_tundra", "toyota", ["tundra"], "pickup"),
    # SUVs - full size
    ("chevrolet_tahoe", "chevrolet", ["tahoe"], "suv"),
    ("chevrolet_suburban", "chevrolet", ["suburban"], "suv"),
    ("ford_expedition", "ford", ["expedition"], "suv"),
    ("gmc_yukon", "gmc", ["yukon"], "suv"),
    # SUVs - mid/compact
    ("ford_explorer", "ford", ["explorer"], "suv"),
    ("chevrolet_equinox", "chevrolet", ["equinox"], "suv"),
    ("honda_cr_v", "honda", ["cr-v", "crv", "cr v"], "suv"),
    ("toyota_rav4", "toyota", ["rav4", "rav 4", "rav-4"], "suv"),
    ("nissan_rogue", "nissan", ["rogue", "x-trail", "xtrail"], "suv"),
    ("hyundai_tucson", "hyundai", ["tucson"], "suv"),
    ("toyota_4runner", "toyota", ["4runner", "4-runner"], "suv"),
    ("toyota_highlander", "toyota", ["highlander", "kluger"], "suv"),
    ("jeep_grand_cherokee", "jeep", ["grand cherokee"], "suv"),
    ("jeep_wrangler", "jeep", ["wrangler"], "suv"),
    ("dodge_durango", "dodge", ["durango"], "suv"),
    ("kia_sorento", "kia", ["sorento"], "suv"),
    # Sedans
    ("honda_accord", "honda", ["accord"], "sedan"),
    ("honda_civic", "honda", ["civic"], "sedan"),
    ("toyota_camry", "toyota", ["camry"], "sedan"),
    ("toyota_corolla", "toyota", ["corolla"], "sedan"),
    ("nissan_altima", "nissan", ["altima"], "sedan"),
    ("nissan_sentra", "nissan", ["sentra", "sylphy"], "sedan"),
    ("hyundai_sonata", "hyundai", ["sonata"], "sedan"),
    ("dodge_charger", "dodge", ["charger"], "sedan"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Synset-Boulevard, filter to canonical 30 classes, materialize ImageFolder.",
    )
    parser.add_argument(
        "--output-root",
        default="data/curated/synset_boulevard_canonical_supplemental_20260509",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/manifests/public/synset-boulevard-canonical-supplemental-20260509.yaml",
    )
    parser.add_argument(
        "--dataset-name",
        default="synset-boulevard-canonical-supplemental-20260509",
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument(
        "--subset",
        default="Bayer_good",
        help="Synset-Boulevard subset name (Bayer_good is cleanest)",
    )
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=200,
        help="Cap synthetic samples per canonical class so they don't dominate real data",
    )
    parser.add_argument(
        "--scan-train",
        action="store_true",
        default=True,
        help="Stream the train split (default true)",
    )
    parser.add_argument(
        "--scan-validation",
        action="store_true",
        default=False,
        help="Also stream the validation split (synthetic validation isn't ideal but adds variety)",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--progress-every", type=int, default=500)
    return parser.parse_args()


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _classify(make: str, model: str) -> tuple[str, str] | None:
    if not make or not model:
        return None
    make_lower = make.strip().lower()
    model_lower = model.strip().lower()
    for canonical_label, make_pattern, substrings, vehicle_class in CLASS_MAPPINGS:
        if make_lower != make_pattern:
            continue
        for needle in substrings:
            if needle in model_lower:
                return canonical_label, vehicle_class
    return None


def _parse_year(model_year: str | None) -> str | None:
    if not model_year:
        return None
    match = re.search(r"((?:19|20)\d{2})", model_year)
    return match.group(1) if match else None


def _scan_split(
    split: str,
    *,
    subset: str,
    max_per_class: int,
    output_root: Path,
    progress_every: int,
):
    from datasets import load_dataset

    ds = load_dataset(
        "FraunhoferIOSB/Synset-Boulevard",
        subset,
        split=split,
        streaming=True,
    )
    by_class: dict[str, int] = defaultdict(int)
    target_classes = {entry[0] for entry in CLASS_MAPPINGS}
    accepted_records: list[dict[str, Any]] = []
    seen_image_hashes: set[str] = set()
    n_seen = 0
    n_kept = 0
    for ex in ds:
        n_seen += 1
        if n_seen % progress_every == 0:
            done_classes = sum(1 for c in target_classes if by_class[c] >= max_per_class)
            print(
                f"  scan[{split}] seen={n_seen} kept={n_kept} "
                f"saturated_classes={done_classes}/{len(target_classes)}"
            )
        if all(by_class[c] >= max_per_class for c in target_classes):
            print(f"  scan[{split}] all classes saturated at {max_per_class}; stopping early")
            break
        match = _classify(ex.get("make"), ex.get("model"))
        if match is None:
            continue
        canonical_label, vehicle_class = match
        if by_class[canonical_label] >= max_per_class:
            continue
        try:
            image = ex["image"]
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=92)
            content = buffer.getvalue()
        except Exception as exc:
            print(f"  scan[{split}] image decode failed at idx={n_seen}: {exc}", file=sys.stderr)
            continue
        digest = hashlib.sha256(content).hexdigest()[:16]
        if digest in seen_image_hashes:
            continue
        seen_image_hashes.add(digest)
        file_name = f"{canonical_label}_{digest}.jpg"
        relative_path = f"splits/train/{canonical_label}/{file_name}"
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        record = {
            "asset_id": f"synset_{canonical_label}_{digest}",
            "relative_path": relative_path,
            "image_file": f"{canonical_label}/{file_name}",
            "class_label": canonical_label,
            "vehicle_class": vehicle_class,
            "vehicle_make": canonical_label.split("_", 1)[0],
            "vehicle_model": "_".join(canonical_label.split("_")[1:]) or canonical_label,
            "vehicle_year": _parse_year(ex.get("model_year")),
            "vehicle_color": (ex.get("color_category") or "").lower() or None,
            "synset_make": ex.get("make"),
            "synset_model": ex.get("model"),
            "synset_class_name": ex.get("class_name"),
            "synset_model_year_raw": ex.get("model_year"),
            "synset_daytime": ex.get("daytime"),
            "synset_contrast": ex.get("contrast"),
            "source_split": split,
        }
        accepted_records.append(record)
        by_class[canonical_label] += 1
        n_kept += 1

    print(
        f"scan[{split}] done: seen={n_seen} kept={n_kept} "
        f"unique_classes={len([c for c in by_class if by_class[c] > 0])}"
    )
    return accepted_records, dict(by_class)


def _write_color_labels(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "image_file",
                "class_label",
                "vehicle_color",
                "vehicle_make",
                "vehicle_model",
                "vehicle_year",
                "synset_class_name",
                "synset_daytime",
                "synset_contrast",
            ],
        )
        writer.writeheader()
        for r in records:
            if not r.get("vehicle_color"):
                continue
            writer.writerow({k: r.get(k) or "" for k in writer.fieldnames})


def _write_labels_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "image_file",
        "class_label",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_color",
        "source_url",
        "license_name",
        "license_url",
        "synset_class_name",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "image_file": r["image_file"],
                    "class_label": r["class_label"],
                    "vehicle_make": r.get("vehicle_make") or "",
                    "vehicle_model": r.get("vehicle_model") or "",
                    "vehicle_year": r.get("vehicle_year") or "",
                    "vehicle_color": r.get("vehicle_color") or "",
                    "source_url": SYNSET_DATASET_URL,
                    "license_name": SYNSET_LICENSE_NAME,
                    "license_url": SYNSET_LICENSE_URL,
                    "synset_class_name": r.get("synset_class_name") or "",
                }
            )


def _write_manifest(
    *,
    output_root: Path,
    manifest_path: Path,
    dataset_name: str,
    dataset_version: str,
    records: list[dict[str, Any]],
) -> None:
    by_class = defaultdict(int)
    for r in records:
        by_class[r["class_label"]] += 1
    assets = []
    for r in records:
        assets.append(
            {
                "asset_id": r["asset_id"],
                "relative_path": r["relative_path"],
                "capture_session_id": f"{dataset_name}_train",
                "timestamp_utc": None,
                "lighting_conditions": ["unknown"],
                "distance_band": None,
                "annotations": ["vehicle_make", "vehicle_model"],
                "tags": [
                    "synset_boulevard",
                    "synthetic_support",
                    f"make_model:{r['class_label']}",
                    f"vehicle_class:{r['vehicle_class']}",
                    f"synset_class:{r.get('synset_class_name') or 'unknown'}",
                    f"synset_daytime:{r.get('synset_daytime') or 'unknown'}",
                    f"synset_contrast:{r.get('synset_contrast') or 'unknown'}",
                    f"vehicle_color:{r.get('vehicle_color') or 'unknown'}",
                    f"source_split:{r['source_split']}",
                ],
                "expected_plate_text": None,
                "vehicle_color": r.get("vehicle_color"),
                "vehicle_make": r.get("vehicle_make"),
                "vehicle_model": r.get("vehicle_model"),
                "vehicle_year": r.get("vehicle_year"),
                "field_eval_candidate": False,
            }
        )
    manifest = {
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "task": "vehicle_make_model_classification",
        "format": "imagefolder",
        "storage_root": str(output_root.resolve()),
        "review_status": "pending",
        "provenance": {
            "source_name": "FraunhoferIOSB/Synset-Boulevard (Hugging Face datasets)",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": SYNSET_LICENSE_NAME,
            "license_reference": SYNSET_DATASET_URL,
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                "Synthetic VMMR data filtered to canonical 30 make/model classes. "
                "All assets land in train split only per ADR-029 synthetic-mix-into-train policy. "
                "Color labels are also extracted into color_labels.csv for downstream color-head training."
            ),
        },
        "annotation_review": None,
        "assets": assets,
        "splits": [
            {
                "split": "train",
                "relative_path": "splits/train",
                "label_path": "splits/train/labels.csv",
                "sample_count": len(records),
                "capture_session_ids": [f"{dataset_name}_train"],
                "tags": [
                    "synset_boulevard",
                    "synthetic_support",
                    "canonical_make_model",
                    "imagefolder",
                ],
            },
        ],
        "notes": (
            "Synset-Boulevard supplemental for canonical-v4. Train-only synthetic; "
            "real validation/holdout splits remain in the canonical-vehicle-make-model "
            "manifest. Per-class samples capped to maintain balance with real data."
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_path)

    if output_root.exists() and any(output_root.iterdir()):
        if not args.overwrite:
            print(f"ERROR: {output_root} not empty; pass --overwrite", file=sys.stderr)
            return 2
        import shutil
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []

    if args.scan_train:
        records, by_class = _scan_split(
            "train",
            subset=args.subset,
            max_per_class=args.max_per_class,
            output_root=output_root,
            progress_every=args.progress_every,
        )
        all_records.extend(records)

    if args.scan_validation:
        records, by_class = _scan_split(
            "validation",
            subset=args.subset,
            max_per_class=args.max_per_class,
            output_root=output_root,
            progress_every=args.progress_every,
        )
        all_records.extend(records)

    _write_labels_csv(output_root / "splits" / "train" / "labels.csv", all_records)
    _write_color_labels(output_root / "color_labels.csv", all_records)
    _write_manifest(
        output_root=output_root,
        manifest_path=manifest_path,
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        records=all_records,
    )

    summary = {
        "dataset_name": args.dataset_name,
        "manifest_path": str(manifest_path),
        "total_records": len(all_records),
        "by_class": {
            cls: sum(1 for r in all_records if r["class_label"] == cls)
            for cls in sorted({r["class_label"] for r in all_records})
        },
        "color_labels_present": sum(1 for r in all_records if r.get("vehicle_color")),
    }
    (output_root / "import_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
