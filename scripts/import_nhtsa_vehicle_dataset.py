from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


NHTSA_API = "https://api.nhtsa.gov/SafetyRatings"
USER_AGENT = "RepoScanProDatasetImporter/1.0 (local training dataset curation)"
SPLITS = ("train", "validation", "holdout")


@dataclass(frozen=True)
class VehicleTarget:
    class_label: str
    make: str
    model: str
    year_start: int
    year_end: int
    model_patterns: tuple[str, ...]
    vehicle_class: str


TARGETS: tuple[VehicleTarget, ...] = (
    VehicleTarget("ford_f_series", "Ford", "f_series", 2010, 2026, (r"\bF-?150\b", r"\bF-?250\b", r"\bF-?350\b", r"\bF SERIES\b"), "pickup"),
    VehicleTarget("chevrolet_silverado", "Chevrolet", "silverado", 2008, 2026, (r"\bSILVERADO\b",), "pickup"),
    VehicleTarget("chevrolet_tahoe", "Chevrolet", "tahoe", 2010, 2026, (r"\bTAHOE\b",), "suv"),
    VehicleTarget("chevrolet_suburban", "Chevrolet", "suburban", 2010, 2026, (r"\bSUBURBAN\b",), "suv"),
    VehicleTarget("ford_expedition", "Ford", "expedition", 2010, 2026, (r"\bEXPEDITION\b",), "suv"),
    VehicleTarget("honda_civic", "Honda", "civic", 2014, 2026, (r"\bCIVIC\b",), "sedan"),
    VehicleTarget("honda_accord", "Honda", "accord", 2014, 2026, (r"\bACCORD\b",), "sedan"),
    VehicleTarget("nissan_altima", "Nissan", "altima", 2015, 2026, (r"\bALTIMA\b",), "sedan"),
    VehicleTarget("nissan_sentra", "Nissan", "sentra", 2015, 2026, (r"\bSENTRA\b",), "sedan"),
    VehicleTarget("ram_pickup", "Ram", "pickup", 2008, 2026, (r"\b1500\b", r"\b2500\b", r"\b3500\b", r"\bRAM\b"), "pickup"),
)

OKLAHOMA_POPULAR_TARGETS: tuple[VehicleTarget, ...] = (
    VehicleTarget("toyota_camry", "Toyota", "camry", 2016, 2026, (r"\bCAMRY\b",), "sedan"),
    VehicleTarget("toyota_tacoma", "Toyota", "tacoma", 2016, 2026, (r"\bTACOMA\b",), "pickup"),
    VehicleTarget("toyota_tundra", "Toyota", "tundra", 2016, 2026, (r"\bTUNDRA\b",), "pickup"),
    VehicleTarget("toyota_rav4", "Toyota", "rav4", 2016, 2026, (r"\bRAV4\b",), "suv"),
    VehicleTarget("gmc_sierra", "GMC", "sierra", 2016, 2026, (r"\bSIERRA\b",), "pickup"),
    VehicleTarget("honda_cr_v", "Honda", "cr_v", 2016, 2026, (r"\bCR-?V\b",), "suv"),
    VehicleTarget("chevrolet_equinox", "Chevrolet", "equinox", 2016, 2026, (r"\bEQUINOX\b",), "suv"),
    VehicleTarget("ford_explorer", "Ford", "explorer", 2016, 2026, (r"\bEXPLORER\b",), "suv"),
    VehicleTarget("nissan_rogue", "Nissan", "rogue", 2016, 2026, (r"\bROGUE\b",), "suv"),
    VehicleTarget("hyundai_tucson", "Hyundai", "tucson", 2016, 2026, (r"\bTUCSON\b",), "suv"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import official NHTSA Safety Ratings vehicle images.")
    parser.add_argument("--output-root", default="data/curated/nhtsa_vehicle_make_model_20260503")
    parser.add_argument("--manifest-path", default="data/manifests/public/nhtsa-vehicle-make-model-20260503.yaml")
    parser.add_argument("--dataset-name", default="nhtsa-vehicle-make-model-20260503")
    parser.add_argument("--dataset-version", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--target-profile", choices=("priority", "oklahoma-popular"), default="priority")
    parser.add_argument("--max-per-class", type=int, default=80)
    parser.add_argument("--thumbnail-size", type=int, default=192)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reuse-discovery", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _selected_targets(args: argparse.Namespace) -> tuple[VehicleTarget, ...]:
    if args.target_profile == "oklahoma-popular":
        return OKLAHOMA_POPULAR_TARGETS
    return TARGETS


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    return "_".join(part for part in re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).split("_") if part)


def _request_json(url: str, *, retries: int = 4) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def _api_url(*parts: str | int) -> str:
    encoded = [urllib.parse.quote(str(part), safe="") for part in parts]
    return f"{NHTSA_API}/{'/'.join(encoded)}"


def _model_matches(target: VehicleTarget, model_name: str) -> bool:
    normalized = re.sub(r"[^A-Z0-9-]+", " ", model_name.upper())
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in target.model_patterns)


def _models_for_year_make(year: int, make: str) -> list[dict[str, Any]]:
    payload = _request_json(_api_url("modelyear", year, "make", make))
    return list(payload.get("Results") or [])


def _vehicle_summaries(year: int, make: str, model: str) -> list[dict[str, Any]]:
    payload = _request_json(_api_url("modelyear", year, "make", make, "model", model))
    return list(payload.get("Results") or [])


def _vehicle_detail(vehicle_id: int) -> dict[str, Any]:
    payload = _request_json(_api_url("VehicleId", vehicle_id))
    results = payload.get("Results") or []
    return dict(results[0]) if results else {}


def _picture_urls(detail: dict[str, Any]) -> list[tuple[str, str]]:
    pictures = []
    for key in ("FrontCrashPicture", "SideCrashPicture", "SidePolePicture"):
        value = str(detail.get(key) or "").strip()
        if value.startswith("http"):
            pictures.append((key, value))
    return pictures


def _download_image(url: str, destination: Path) -> bool:
    if destination.exists():
        try:
            with Image.open(destination) as image:
                image.verify()
            return True
        except (UnidentifiedImageError, OSError):
            destination.unlink(missing_ok=True)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"WARN: skipped unavailable image {url}: {exc}")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    try:
        with Image.open(destination) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        destination.unlink(missing_ok=True)
        return False
    return True


def _discover_candidates(args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    targets = _selected_targets(args)
    discovered: dict[str, list[dict[str, Any]]] = {target.class_label: [] for target in targets}
    seen_vehicle_ids: set[int] = set()

    for target in targets:
        for year in range(target.year_start, min(target.year_end, datetime.now().year) + 1):
            try:
                models = _models_for_year_make(year, target.make)
            except Exception as exc:
                print(f"WARN: failed model list for {target.make} {year}: {exc}")
                continue

            matching_models = sorted({str(row.get("Model") or "").strip() for row in models if _model_matches(target, str(row.get("Model") or ""))})
            for model_name in matching_models:
                if len(discovered[target.class_label]) >= args.max_per_class:
                    break
                try:
                    summaries = _vehicle_summaries(year, target.make, model_name)
                except Exception as exc:
                    print(f"WARN: failed summaries for {target.make} {model_name} {year}: {exc}")
                    continue

                for summary in summaries:
                    vehicle_id = int(summary.get("VehicleId") or 0)
                    if vehicle_id <= 0 or vehicle_id in seen_vehicle_ids:
                        continue
                    try:
                        detail = _vehicle_detail(vehicle_id)
                    except Exception as exc:
                        print(f"WARN: failed detail for vehicle {vehicle_id}: {exc}")
                        continue
                    pictures = _picture_urls(detail)
                    if not pictures:
                        continue
                    seen_vehicle_ids.add(vehicle_id)
                    discovered[target.class_label].append(
                        {
                            "class_label": target.class_label,
                            "year": year,
                            "make": target.make,
                            "model": target.model,
                            "model_query": model_name,
                            "vehicle_id": vehicle_id,
                            "description": detail.get("VehicleDescription") or summary.get("VehicleDescription") or "",
                            "nhtsa_make": detail.get("Make") or "",
                            "nhtsa_model": detail.get("Model") or model_name,
                            "vehicle_class": target.vehicle_class,
                            "pictures": [{"type": picture_type, "url": url} for picture_type, url in pictures],
                        }
                    )
                    if len(discovered[target.class_label]) >= args.max_per_class:
                        break
                    time.sleep(args.sleep_seconds)
    return discovered


def _split_items(items: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(args.seed)
    shuffled = list(items)
    rng.shuffle(shuffled)
    train_count = int(len(shuffled) * args.train_ratio)
    validation_count = int(len(shuffled) * args.validation_ratio)
    return {
        "train": shuffled[:train_count],
        "validation": shuffled[train_count : train_count + validation_count],
        "holdout": shuffled[train_count + validation_count :],
    }


def _make_asset_id(item: dict[str, Any], picture: dict[str, str]) -> str:
    digest = hashlib.sha1(f"{item['vehicle_id']}:{picture['type']}:{picture['url']}".encode("utf-8")).hexdigest()[:12]
    return f"nhtsa-{item['vehicle_id']}-{_slug(picture['type'])}-{digest}"


def _build_dataset(discovered: dict[str, list[dict[str, Any]]], output_root: Path, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    assets: list[dict[str, Any]] = []
    split_counts: dict[str, int] = {split: 0 for split in SPLITS}
    label_rows: list[dict[str, str]] = []

    for class_label, items in discovered.items():
        split_map = _split_items(items, args)
        for split_name, split_items in split_map.items():
            sample_count = 0
            for item in split_items:
                for picture in item["pictures"]:
                    asset_id = _make_asset_id(item, picture)
                    ext = Path(urllib.parse.urlparse(picture["url"]).path).suffix.lower() or ".jpg"
                    relative_path = Path("splits") / split_name / class_label / f"{asset_id}{ext}"
                    destination = output_root / relative_path
                    if not args.dry_run and not _download_image(picture["url"], destination):
                        continue
                    sample_count += 1
                    assets.append(
                        {
                            "asset_id": asset_id,
                            "relative_path": str(relative_path).replace("\\", "/"),
                            "capture_session_id": f"{args.dataset_name}_{split_name}",
                            "timestamp_utc": None,
                            "lighting_conditions": ["unknown"],
                            "distance_band": None,
                            "annotations": ["vehicle_make", "vehicle_model"],
                            "tags": [
                                "nhtsa_safety_ratings",
                                f"make_model:{class_label}",
                                f"target_year_range:{_target_by_label(class_label).year_start}-{_target_by_label(class_label).year_end}",
                                f"vehicle_class:{item['vehicle_class']}",
                                f"nhtsa_picture:{picture['type']}",
                                "review_required:crash_test_context",
                            ],
                            "expected_plate_text": None,
                            "vehicle_color": None,
                            "vehicle_make": str(item["make"]).lower(),
                            "vehicle_model": str(item["model"]).lower(),
                            "vehicle_year": str(item["year"]),
                            "field_eval_candidate": True,
                        }
                    )
                    label_rows.append(
                        {
                            "asset_id": asset_id,
                            "split": split_name,
                            "class_label": class_label,
                            "vehicle_make": str(item["make"]).lower(),
                            "vehicle_model": str(item["model"]).lower(),
                            "vehicle_year": str(item["year"]),
                            "vehicle_id": str(item["vehicle_id"]),
                            "description": str(item["description"]),
                            "picture_type": picture["type"],
                            "source_url": picture["url"],
                        }
                    )
            split_counts[split_name] += sample_count
    splits = [
        {
            "split": split_name,
            "relative_path": str(Path("splits") / split_name).replace("\\", "/"),
            "label_path": "metadata/labels.csv",
            "sample_count": sample_count,
        }
        for split_name, sample_count in split_counts.items()
        if sample_count
    ]
    return assets, splits, label_rows


def _target_by_label(class_label: str) -> VehicleTarget:
    for target in (*TARGETS, *OKLAHOMA_POPULAR_TARGETS):
        if target.class_label == class_label:
            return target
    raise KeyError(class_label)


def _write_labels(output_root: Path, label_rows: list[dict[str, str]]) -> None:
    metadata_dir = output_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    labels_path = metadata_dir / "labels.csv"
    columns = [
        "asset_id",
        "split",
        "class_label",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_id",
        "description",
        "picture_type",
        "source_url",
    ]
    with labels_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(label_rows)


def _write_manifest(manifest_path: Path, output_root: Path, assets: list[dict[str, Any]], splits: list[dict[str, Any]], args: argparse.Namespace) -> None:
    manifest = {
        "dataset_name": args.dataset_name,
        "dataset_version": args.dataset_version,
        "task": "vehicle_make_model_classification",
        "format": "imagefolder",
        "storage_root": str(output_root.resolve()),
        "review_status": "pending",
        "provenance": {
            "source_name": "NHTSA Safety Ratings API crash test images",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": "Official NHTSA hosted imagery; verify reuse policy before commercial training release",
            "license_reference": "https://api.nhtsa.gov/SafetyRatings",
            "region": "US",
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": "Images are exact year/make/model official crash-test context examples, useful as supplemental robustness data after visual review.",
        },
        "annotation_review": {
            "reviewer": "pending",
            "reviewed_at_utc": _utcnow(),
            "accepted_tasks": ["vehicle_make", "vehicle_model"],
            "notes": "Pending visual review because NHTSA images often show damaged vehicles and crash-test positioning.",
        },
        "assets": assets,
        "splits": splits,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def _write_contact_sheet(output_root: Path, label_rows: list[dict[str, str]], thumbnail_size: int) -> None:
    if not label_rows:
        return
    image_paths = []
    for row in label_rows[:120]:
        matches = list((output_root / "splits" / row["split"] / row["class_label"]).glob(f"{row['asset_id']}.*"))
        if matches:
            image_paths.append((matches[0], row))

    columns = 5
    label_height = 52
    rows = (len(image_paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumbnail_size, rows * (thumbnail_size + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, (path, row) in enumerate(image_paths):
        x = (index % columns) * thumbnail_size
        y = (index // columns) * (thumbnail_size + label_height)
        try:
            with Image.open(path) as image:
                image.thumbnail((thumbnail_size, thumbnail_size))
                sheet.paste(image.convert("RGB"), (x + (thumbnail_size - image.width) // 2, y))
        except OSError:
            continue
        label = f"{row['class_label']}\n{row['vehicle_year']} {row['picture_type']}"
        draw.text((x + 4, y + thumbnail_size + 4), label, fill="black", font=font)

    sheet.save(output_root / "review_contact_sheet.jpg", quality=90)


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    if output_root.exists() and args.overwrite and not args.dry_run and not args.reuse_discovery:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    discovery_path = output_root / "metadata" / "nhtsa_discovery.json"
    discovery_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reuse_discovery and discovery_path.exists():
        discovered = json.loads(discovery_path.read_text(encoding="utf-8"))
    else:
        discovered = _discover_candidates(args)
        discovery_path.write_text(json.dumps(discovered, indent=2), encoding="utf-8")

    assets, splits, label_rows = _build_dataset(discovered, output_root, args)
    if not args.dry_run:
        _write_labels(output_root, label_rows)
        _write_manifest(manifest_path, output_root, assets, splits, args)
        _write_contact_sheet(output_root, label_rows, args.thumbnail_size)

    print("Imported NHTSA vehicle image candidates")
    for class_label, items in discovered.items():
        image_count = sum(len(item["pictures"]) for item in items)
        print(f"- {class_label}: vehicles={len(items)} images={image_count}")
    print(f"Assets written: {len(assets)}")
    print(f"Output root: {output_root}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
