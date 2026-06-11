"""Second-wave Synset-Boulevard supplemental for canonical-v5.

Filters the FraunhoferIOSB/Synset-Boulevard CC-BY-4.0 synthetic VMMR
dataset for the 10 new canonical-v5 classes plus a couple of existing
classes that may have additional coverage we missed in the first
pass. Reuses the same streaming + matching pattern as the 20260509
importer but with a v5 class-mapping set so the output is separable
from the 20260509 dataset and can be unioned cleanly.

Output: data/curated/synset_boulevard_canonical_v5_supplemental_20260518/
Manifest: data/manifests/public/synset-boulevard-canonical-v5-supplemental-20260518.yaml
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SYNSET_LICENSE_NAME = "CC-BY-4.0"
SYNSET_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SYNSET_DATASET_URL = "https://huggingface.co/datasets/FraunhoferIOSB/Synset-Boulevard"


# Class mappings focused on the canonical-v5 new classes. Synset-Boulevard is
# European-skewed so only some of these will have hits — that is expected.
CLASS_MAPPINGS = [
    ("cadillac_escalade", "cadillac", ["escalade"], "suv"),
    ("lincoln_navigator", "lincoln", ["navigator"], "suv"),
    ("honda_pilot", "honda", ["pilot"], "suv"),
    ("ford_escape", "ford", ["escape", "kuga"], "suv"),
    ("hyundai_elantra", "hyundai", ["elantra", "avante"], "sedan"),
    ("subaru_outback", "subaru", ["outback", "legacy outback"], "suv"),
    ("kia_sportage", "kia", ["sportage"], "suv"),
    ("hyundai_santa_fe", "hyundai", ["santa fe", "santa-fe", "santafe", "maxcruz"], "suv"),
    ("chevrolet_malibu", "chevrolet", ["malibu"], "sedan"),
    ("volkswagen_jetta", "volkswagen", ["jetta", "vento"], "sedan"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synset-Boulevard supplemental for canonical-v5 (10 new classes)."
    )
    parser.add_argument(
        "--output-root",
        default="data/curated/synset_boulevard_canonical_v5_supplemental_20260518",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/manifests/public/synset-boulevard-canonical-v5-supplemental-20260518.yaml",
    )
    parser.add_argument(
        "--dataset-name",
        default="synset-boulevard-canonical-v5-supplemental-20260518",
    )
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--subset", default="Bayer_good")
    parser.add_argument("--max-per-class", type=int, default=200)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--progress-every", type=int, default=1000)
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
            "asset_id": f"synset_v5_{canonical_label}_{digest}",
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
            "source_name": "FraunhoferIOSB/Synset-Boulevard (Hugging Face) v5 second wave",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": SYNSET_LICENSE_NAME,
            "license_reference": SYNSET_DATASET_URL,
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": (
                "Synthetic VMMR data filtered to the 10 canonical-v5 new classes "
                "(Escalade, Navigator, Pilot, Escape, Elantra, Outback, Sportage, "
                "Santa Fe, Malibu, Jetta). Train-only per ADR-029."
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
                    "canonical_make_model_v5",
                    "imagefolder",
                ],
            },
        ],
        "notes": (
            "Second-wave Synset-Boulevard supplemental for canonical-v5. Synset is "
            "European-skewed; expect lower yield than the 20260509 first wave."
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
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    records, _by_class = _scan_split(
        "train",
        subset=args.subset,
        max_per_class=args.max_per_class,
        output_root=output_root,
        progress_every=args.progress_every,
    )

    _write_labels_csv(output_root / "splits" / "train" / "labels.csv", records)
    _write_manifest(
        output_root=output_root,
        manifest_path=manifest_path,
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        records=records,
    )

    summary = {
        "dataset_name": args.dataset_name,
        "manifest_path": str(manifest_path),
        "total_records": len(records),
        "by_class": {
            cls: sum(1 for r in records if r["class_label"] == cls)
            for cls in sorted({r["class_label"] for r in records})
        },
        "color_labels_present": sum(1 for r in records if r.get("vehicle_color")),
    }
    (output_root / "import_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
