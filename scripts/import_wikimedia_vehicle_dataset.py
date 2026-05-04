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
from PIL import Image, UnidentifiedImageError


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "RepoScanProDatasetImporter/1.0 (local training dataset curation)"

USABLE_LICENSE_PREFIXES = (
    "cc0",
    "cc by",
    "cc-by",
    "cc by-sa",
    "cc-by-sa",
    "public domain",
    "pd",
)

SPLITS = ("train", "validation", "holdout")


@dataclass(frozen=True)
class VehicleTarget:
    class_label: str
    make: str
    model: str
    year_start: int
    year_end: int
    search_names: tuple[str, ...]
    vehicle_class: str
    commons_categories: tuple[str, ...] = ()


TARGETS: tuple[VehicleTarget, ...] = (
    VehicleTarget(
        "ford_f_series",
        "ford",
        "f_series",
        2010,
        2026,
        ("Ford F-Series", "Ford F-150", "Ford F-250", "Ford Super Duty"),
        "pickup",
        ("Ford F-150 (twelfth generation)", "Ford F-150 (thirteenth generation)", "Ford F-150 (fourteenth generation)", "Ford F-Series (2015)"),
    ),
    VehicleTarget(
        "chevrolet_silverado",
        "chevrolet",
        "silverado",
        2008,
        2026,
        ("Chevrolet Silverado", "Chevy Silverado"),
        "pickup",
        ("Chevrolet Silverado (GMT901/GMT911)", "Chevrolet Silverado (GMTK2EC)", "Chevrolet Silverado (GMTK2RC)", "Chevrolet Silverado (GMTK2CC)", "Chevrolet Silverado (GMTT1XX)"),
    ),
    VehicleTarget("chevrolet_tahoe", "chevrolet", "tahoe", 2010, 2026, ("Chevrolet Tahoe", "Chevy Tahoe"), "suv", ("Chevrolet Tahoe",)),
    VehicleTarget(
        "chevrolet_suburban",
        "chevrolet",
        "suburban",
        2010,
        2026,
        ("Chevrolet Suburban", "Chevy Suburban"),
        "suv",
        ("Chevrolet Suburban", "Chevrolet Suburban (GMTT1YC)"),
    ),
    VehicleTarget("ford_expedition", "ford", "expedition", 2010, 2026, ("Ford Expedition",), "suv", ("Ford Expedition",)),
    VehicleTarget("honda_civic", "honda", "civic", 2014, 2026, ("Honda Civic",), "sedan", ("Honda Civic (2015)", "Honda Civic")),
    VehicleTarget("honda_accord", "honda", "accord", 2014, 2026, ("Honda Accord",), "sedan", ("Honda Accord (2017)", "Honda Accord (2022)", "Honda Accord")),
    VehicleTarget("nissan_altima", "nissan", "altima", 2015, 2026, ("Nissan Altima",), "sedan", ("Nissan Altima (L33)", "Nissan Altima (L34)", "Nissan Altima")),
    VehicleTarget("nissan_sentra", "nissan", "sentra", 2015, 2026, ("Nissan Sentra",), "sedan", ("Nissan Sentra (B18)", "Nissan Sentra")),
    VehicleTarget(
        "ram_pickup",
        "ram",
        "pickup",
        2008,
        2026,
        ("Ram pickup", "Dodge Ram", "Ram 1500", "Ram 2500"),
        "pickup",
        ("Ram Pickup (fifth generation)", "Ram 1500 (DS)", "Ram 1500 (DT)", "Dodge Ram 1500", "Dodge DS/DJ Ram 1500"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import usable Wikimedia Commons vehicle images into a RepoScan ImageFolder dataset."
    )
    parser.add_argument("--output-root", default="data/curated/wikimedia_priority_vehicle_make_model_20260503")
    parser.add_argument("--manifest-path", default="data/manifests/public/wikimedia-priority-vehicle-make-model-20260503.yaml")
    parser.add_argument("--dataset-name", default="wikimedia-priority-vehicle-make-model-20260503")
    parser.add_argument("--dataset-version", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--max-per-class", type=int, default=40)
    parser.add_argument("--search-limit", type=int, default=25)
    parser.add_argument("--thumbnail-width", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--sleep-seconds", type=float, default=1.2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    return "_".join(part for part in re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).split("_") if part)


def _request_json(params: dict[str, Any], *, retries: int = 5) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{COMMONS_API}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable")


def _search_pages(query: str, *, limit: int) -> list[int]:
    payload = _request_json(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": f'intitle:"{query}"',
            "gsrlimit": limit,
            "prop": "info",
        }
    )
    pages = payload.get("query", {}).get("pages", {})
    return [int(page_id) for page_id in pages]


def _page_image_infos(page_ids: list[int], *, thumbnail_width: int) -> list[dict[str, Any]]:
    if not page_ids:
        return []
    payload = _request_json(
        {
            "action": "query",
            "format": "json",
            "pageids": "|".join(str(page_id) for page_id in page_ids[:50]),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": thumbnail_width,
        }
    )
    infos: list[dict[str, Any]] = []
    for page_id, page in (payload.get("query", {}).get("pages", {}) or {}).items():
        image_info = (page.get("imageinfo") or [{}])[0]
        ext = image_info.get("extmetadata") or {}
        infos.append(
            {
                "page_id": int(page_id),
                "title": page.get("title", ""),
                "url": image_info.get("thumburl") or image_info.get("url", ""),
                "original_url": image_info.get("url", ""),
                "description_url": image_info.get("descriptionurl", ""),
                "mime": image_info.get("mime", ""),
                "width": image_info.get("thumbwidth") or image_info.get("width"),
                "height": image_info.get("thumbheight") or image_info.get("height"),
                "license_short_name": _metadata_value(ext, "LicenseShortName"),
                "license_url": _metadata_value(ext, "LicenseUrl"),
                "usage_terms": _metadata_value(ext, "UsageTerms"),
                "artist": _metadata_value(ext, "Artist"),
                "credit": _metadata_value(ext, "Credit"),
            }
        )
    return infos


def _category_image_infos(category: str, *, limit: int, thumbnail_width: int) -> list[dict[str, Any]]:
    payload = _request_json(
        {
            "action": "query",
            "format": "json",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmtype": "file",
            "gcmlimit": min(limit, 50),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": thumbnail_width,
        }
    )
    infos: list[dict[str, Any]] = []
    for page_id, page in (payload.get("query", {}).get("pages", {}) or {}).items():
        image_info = (page.get("imageinfo") or [{}])[0]
        ext = image_info.get("extmetadata") or {}
        infos.append(
            {
                "page_id": int(page_id),
                "title": page.get("title", ""),
                "url": image_info.get("thumburl") or image_info.get("url", ""),
                "original_url": image_info.get("url", ""),
                "description_url": image_info.get("descriptionurl", ""),
                "mime": image_info.get("mime", ""),
                "width": image_info.get("thumbwidth") or image_info.get("width"),
                "height": image_info.get("thumbheight") or image_info.get("height"),
                "license_short_name": _metadata_value(ext, "LicenseShortName"),
                "license_url": _metadata_value(ext, "LicenseUrl"),
                "usage_terms": _metadata_value(ext, "UsageTerms"),
                "artist": _metadata_value(ext, "Artist"),
                "credit": _metadata_value(ext, "Credit"),
            }
        )
    return infos


def _metadata_value(extmetadata: dict[str, Any], key: str) -> str:
    value = extmetadata.get(key, {})
    return str(value.get("value", "") or "").strip()


def _license_is_usable(info: dict[str, Any]) -> bool:
    text = f"{info.get('license_short_name', '')} {info.get('usage_terms', '')}".lower()
    return any(prefix in text for prefix in USABLE_LICENSE_PREFIXES)


def _download_image(url: str, destination: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    try:
        with Image.open(destination) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        destination.unlink(missing_ok=True)
        return False
    return True


def _year_terms(target: VehicleTarget) -> list[int]:
    mid = target.year_start + ((target.year_end - target.year_start) // 2)
    return sorted({target.year_start, mid, target.year_end})


def _queries_for_target(target: VehicleTarget) -> list[str]:
    queries: list[str] = []
    for name in target.search_names[:2]:
        queries.append(name)
        for year in _year_terms(target):
            queries.append(f"{year} {name}")
    return queries


def _prepare_output(output_root: Path, manifest_path: Path, overwrite: bool) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{output_root} is not empty; pass --overwrite to replace it")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)


def _split_records(records: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(args.seed)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["class_label"], []).append(record)

    result = {split: [] for split in SPLITS}
    for class_records in grouped.values():
        rng.shuffle(class_records)
        count = len(class_records)
        train_count = int(count * args.train_ratio)
        validation_count = int(count * args.validation_ratio)
        if count >= 3:
            train_count = max(1, train_count)
            validation_count = max(1, validation_count)
            holdout_count = max(1, count - train_count - validation_count)
            while train_count + validation_count + holdout_count > count:
                train_count -= 1
        else:
            validation_count = 0
            holdout_count = 0
        result["train"].extend(class_records[:train_count])
        result["validation"].extend(class_records[train_count : train_count + validation_count])
        result["holdout"].extend(class_records[train_count + validation_count :])
    return result


def _write_labels_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "image_file",
                "class_label",
                "vehicle_make",
                "vehicle_model",
                "vehicle_year",
                "source_url",
                "license_name",
                "license_url",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames})


def _write_manifest(
    *,
    output_root: Path,
    manifest_path: Path,
    args: argparse.Namespace,
    split_records: dict[str, list[dict[str, Any]]],
) -> None:
    assets: list[dict[str, Any]] = []
    for split_name, rows in split_records.items():
        for row in rows:
            assets.append(
                {
                    "asset_id": row["asset_id"],
                    "relative_path": row["relative_path"],
                    "capture_session_id": f"{args.dataset_name}_{split_name}",
                    "timestamp_utc": None,
                    "lighting_conditions": ["unknown"],
                    "distance_band": None,
                    "annotations": ["vehicle_make", "vehicle_model"],
                    "tags": [
                        "wikimedia_commons",
                        f"make_model:{row['class_label']}",
                        f"vehicle_class:{row['vehicle_class']}",
                        f"target_year_range:{row['target_year_range']}",
                        f"source_page_id:{row['page_id']}",
                    ],
                    "expected_plate_text": None,
                    "vehicle_color": None,
                    "vehicle_make": row["vehicle_make"],
                    "vehicle_model": row["vehicle_model"],
                    "vehicle_year": row["vehicle_year"],
                    "field_eval_candidate": False,
                }
            )

    manifest = {
        "dataset_name": args.dataset_name,
        "dataset_version": args.dataset_version,
        "task": "vehicle_make_model_classification",
        "format": "imagefolder",
        "storage_root": str(output_root.resolve()),
        "review_status": "pending",
        "provenance": {
            "source_name": "Wikimedia Commons API",
            "source_kind": "public_benchmark",
            "license_tier": "public",
            "license_name": "Per-image Wikimedia Commons license metadata",
            "license_reference": "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia",
            "region": None,
            "collected_by": "codex",
            "collection_start_utc": None,
            "collection_end_utc": _utcnow(),
            "notes": "Images were filtered to public-domain or Creative Commons-style license metadata and require visual review before approval.",
        },
        "annotation_review": None,
        "assets": assets,
        "splits": [
            {
                "split": split_name,
                "relative_path": f"splits/{split_name}",
                "label_path": f"splits/{split_name}/labels.csv",
                "sample_count": len(rows),
                "capture_session_ids": [f"{args.dataset_name}_{split_name}"],
                "tags": ["wikimedia_commons", "priority_vehicle_make_model", "pending_visual_review"],
            }
            for split_name, rows in split_records.items()
        ],
        "notes": "Priority make/model vehicle dataset imported from Wikimedia Commons. Keep pending until images are visually reviewed for exact class labels.",
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False), encoding="utf-8")


def import_target(target: VehicleTarget, *, output_root: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_page_ids: set[int] = set()
    seen_hashes: set[str] = set()
    for category in target.commons_categories:
        if len(records) >= args.max_per_class:
            break
        try:
            image_infos = _category_image_infos(
                category,
                limit=args.search_limit,
                thumbnail_width=args.thumbnail_width,
            )
        except Exception as exc:
            print(f"warning: category failed for {category!r}: {exc}", file=sys.stderr)
            time.sleep(args.sleep_seconds)
            continue
        for info in image_infos:
            if len(records) >= args.max_per_class:
                break
            if info["page_id"] in seen_page_ids:
                continue
            seen_page_ids.add(info["page_id"])
            record = _maybe_download_record(target, info, output_root=output_root, args=args, seen_hashes=seen_hashes)
            if record is not None:
                records.append(record)
                print(f"{target.class_label}: imported {len(records)}/{args.max_per_class} from category {category}")
                time.sleep(args.sleep_seconds)
        time.sleep(args.sleep_seconds)
    for query in _queries_for_target(target):
        if len(records) >= args.max_per_class:
            break
        try:
            page_ids = _search_pages(query, limit=args.search_limit)
        except Exception as exc:
            print(f"warning: search failed for {query!r}: {exc}", file=sys.stderr)
            continue
        page_ids = [page_id for page_id in page_ids if page_id not in seen_page_ids]
        seen_page_ids.update(page_ids)
        try:
            image_infos = _page_image_infos(page_ids, thumbnail_width=args.thumbnail_width)
        except Exception as exc:
            print(f"warning: metadata failed for query {query!r}: {exc}", file=sys.stderr)
            time.sleep(args.sleep_seconds)
            continue
        for info in image_infos:
            if len(records) >= args.max_per_class:
                break
            record = _maybe_download_record(target, info, output_root=output_root, args=args, seen_hashes=seen_hashes)
            if record is not None:
                records.append(record)
                print(f"{target.class_label}: imported {len(records)}/{args.max_per_class} from page {info['page_id']}")
                time.sleep(args.sleep_seconds)
        time.sleep(args.sleep_seconds)
    return records


def _maybe_download_record(
    target: VehicleTarget,
    info: dict[str, Any],
    *,
    output_root: Path,
    args: argparse.Namespace,
    seen_hashes: set[str],
) -> dict[str, Any] | None:
    page_id = info["page_id"]
    if not str(info.get("mime", "")).lower().startswith("image/"):
        return None
    if not info.get("url") or not _license_is_usable(info):
        return None
    suffix = Path(urllib.parse.urlparse(info["url"]).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    digest_source = f"{page_id}:{info['url']}".encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()[:16]
    filename = f"{target.class_label}_{digest}{suffix}"
    staging_path = output_root / "_downloaded" / target.class_label / filename
    if not args.dry_run:
        try:
            if not _download_image(info["url"], staging_path):
                return None
            content_hash = hashlib.sha256(staging_path.read_bytes()).hexdigest()
            if content_hash in seen_hashes:
                staging_path.unlink(missing_ok=True)
                return None
            seen_hashes.add(content_hash)
        except Exception as exc:
            print(f"warning: download failed for {info['url']}: {exc}", file=sys.stderr)
            return None
    return {
        "asset_id": f"{target.class_label}_{digest}",
        "class_label": target.class_label,
        "vehicle_make": target.make,
        "vehicle_model": target.model,
        "vehicle_year": _extract_year(info["title"], target),
        "vehicle_class": target.vehicle_class,
        "target_year_range": f"{target.year_start}-{target.year_end}",
        "image_file": filename,
        "downloaded_path": str(staging_path),
        "page_id": page_id,
        "source_url": info["description_url"] or info["url"],
        "license_name": info["license_short_name"] or info["usage_terms"],
        "license_url": info["license_url"],
    }


def _extract_year(title: str, target: VehicleTarget) -> str | None:
    years = [int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", title)]
    for year in years:
        if target.year_start <= year <= target.year_end:
            return str(year)
    return None


def _materialize_splits(output_root: Path, split_records: dict[str, list[dict[str, Any]]], dry_run: bool) -> None:
    for split_name, rows in split_records.items():
        for row in rows:
            relative_path = f"splits/{split_name}/{row['class_label']}/{row['image_file']}"
            row["relative_path"] = relative_path
            row["image_file"] = f"{row['class_label']}/{row['image_file']}"
            if dry_run:
                continue
            destination = output_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(row["downloaded_path"], destination)
        _write_labels_csv(output_root / "splits" / split_name / "labels.csv", rows)
    if not dry_run:
        shutil.rmtree(output_root / "_downloaded", ignore_errors=True)


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_path)
    _prepare_output(output_root, manifest_path, args.overwrite)

    all_records: list[dict[str, Any]] = []
    for target in TARGETS:
        all_records.extend(import_target(target, output_root=output_root, args=args))

    split_records = _split_records(all_records, args)
    _materialize_splits(output_root, split_records, args.dry_run)
    _write_manifest(output_root=output_root, manifest_path=manifest_path, args=args, split_records=split_records)

    summary = {
        "dataset_name": args.dataset_name,
        "total_samples": len(all_records),
        "classes": {
            target.class_label: sum(1 for record in all_records if record["class_label"] == target.class_label)
            for target in TARGETS
        },
        "splits": {split: len(rows) for split, rows in split_records.items()},
        "manifest_path": str(manifest_path),
    }
    (output_root / "import_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
