from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_CAPTURE_ROOT = Path(r"C:\ReposcanCaptureData\incoming")
DEFAULT_STATE_PATH = Path("runtime/capture_import_state/mobile_capture_import_state.json")

REVIEW_INDEX_FIELDNAMES = [
    "asset_id",
    "capture_session_id",
    "source_capture_id",
    "image_relative_path",
    "metadata_relative_path",
    "timestamp_utc",
    "capture_type",
    "device_label",
    "remote_address",
    "gps_latitude",
    "gps_longitude",
    "gps_accuracy_meters",
    "heading_degrees",
    "speed_mps",
    "reposcan_reviewed",
    "reposcan_accepted",
    "reviewer_notes",
]


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import mobile PWA captures into a RepoScan generic-capture intake manifest."
    )
    parser.add_argument("--capture-root", default=str(DEFAULT_CAPTURE_ROOT))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--review-csv")
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--dataset-version", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument(
        "--task",
        choices=["vehicle_detection", "plate_detection"],
        default="vehicle_detection",
    )
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--session-filter", nargs="*")
    parser.add_argument("--capture-type-filter", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--copy-mode", choices=["copy", "hardlink"], default="hardlink")
    parser.add_argument("--overwrite-manifest", action="store_true")
    parser.add_argument("--reset-state", action="store_true")
    return parser.parse_args()


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = [character if character.isalnum() else "_" for character in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or "unknown"


def _write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_state(path: Path, *, reset: bool) -> dict[str, Any]:
    if reset or not path.exists():
        return {"imported_metadata_paths": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"imported_metadata_paths": []}
    if not isinstance(payload, dict):
        return {"imported_metadata_paths": []}
    imported = payload.get("imported_metadata_paths")
    if not isinstance(imported, list):
        imported = []
    return {"imported_metadata_paths": [str(item) for item in imported]}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    _write_json(path, state)


def _copy_or_link(source: Path, destination: Path, *, copy_mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    if copy_mode == "hardlink":
        try:
            destination.hardlink_to(source)
            return
        except OSError:
            pass
    shutil.copy2(source, destination)


def _normalize_capture_type_filters(raw_filters: list[str] | None) -> set[str] | None:
    if not raw_filters:
        return None
    return {_slugify(item) for item in raw_filters if str(item).strip()}


def _discover_capture_records(
    capture_root: Path,
    *,
    session_filters: set[str] | None,
    capture_type_filters: set[str] | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for metadata_path in sorted(capture_root.rglob("*.json")):
        if metadata_path.name.lower() == "captures.jsonl":
            continue
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        session_id = _slugify(payload.get("sessionId"))
        capture_type = _slugify(payload.get("captureType"))

        if session_filters and session_id not in session_filters:
            continue
        if capture_type_filters and capture_type not in capture_type_filters:
            continue

        image_filename = str(payload.get("imageFilename") or "").strip()
        image_path = metadata_path.with_suffix(".jpg")
        if image_filename:
            candidate = metadata_path.parent / image_filename
            if candidate.exists():
                image_path = candidate
        if not image_path.exists() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue

        relative_metadata_path = metadata_path.relative_to(capture_root)
        relative_image_path = image_path.relative_to(capture_root)
        timestamp_utc = str(payload.get("timestampUtc") or "")
        records.append(
            {
                "source_metadata_path": metadata_path,
                "source_image_path": image_path,
                "relative_metadata_path": relative_metadata_path,
                "relative_image_path": relative_image_path,
                "session_id": session_id,
                "capture_type": capture_type,
                "timestamp_utc": timestamp_utc,
                "payload": payload,
            }
        )

    records.sort(key=lambda item: (item["timestamp_utc"], str(item["relative_image_path"])))
    return records


def _build_asset_id(relative_image_path: Path, payload: dict[str, Any]) -> str:
    day = relative_image_path.parts[0] if len(relative_image_path.parts) >= 1 else "unknown_day"
    session = _slugify(payload.get("sessionId"))
    capture_id = _slugify(payload.get("captureId") or relative_image_path.stem)
    return f"mobile_capture_{_slugify(day)}_{session}_{capture_id}"


def _build_tags(payload: dict[str, Any], *, capture_type: str) -> list[str]:
    tags = ["mobile_capture", "pwa_capture", f"capture_type:{capture_type}"]
    device_label = _slugify(payload.get("deviceLabel"))
    if device_label != "unknown":
        tags.append(f"device:{device_label}")
    if capture_type == "vehicle":
        tags.append("vehicle_candidate")
    if capture_type == "plate":
        tags.append("plate_candidate")
    return tags


def _build_review_row(asset: dict[str, Any], payload: dict[str, Any], *, metadata_relative_path: str) -> dict[str, Any]:
    gps = payload.get("gps") if isinstance(payload.get("gps"), dict) else {}
    return {
        "asset_id": asset["asset_id"],
        "capture_session_id": asset["capture_session_id"],
        "source_capture_id": str(payload.get("captureId") or ""),
        "image_relative_path": asset["relative_path"],
        "metadata_relative_path": metadata_relative_path,
        "timestamp_utc": str(payload.get("timestampUtc") or ""),
        "capture_type": _slugify(payload.get("captureType")),
        "device_label": str(payload.get("deviceLabel") or ""),
        "remote_address": str(payload.get("remoteAddress") or ""),
        "gps_latitude": gps.get("latitude", ""),
        "gps_longitude": gps.get("longitude", ""),
        "gps_accuracy_meters": gps.get("accuracyMeters", ""),
        "heading_degrees": payload.get("headingDegrees", ""),
        "speed_mps": payload.get("speedMps", ""),
        "reposcan_reviewed": "false",
        "reposcan_accepted": "false",
        "reviewer_notes": "",
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.dataset import (
        DatasetAssetRecord,
        DatasetFormat,
        DatasetLicenseTier,
        DatasetProvenance,
        DatasetReviewStatus,
        DatasetSourceKind,
        DatasetTask,
        LightingCondition,
        TrainingDatasetManifest,
    )

    args = parse_args()
    capture_root = Path(args.capture_root).resolve()
    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    review_csv = Path(args.review_csv).resolve() if args.review_csv else output_root / "metadata" / "review_index.csv"
    state_path = (repo_root / args.state_path).resolve() if not Path(args.state_path).is_absolute() else Path(args.state_path).resolve()

    if not capture_root.exists():
        raise FileNotFoundError(f"capture root does not exist: {capture_root}")
    if manifest_path.exists() and not args.overwrite_manifest:
        raise FileExistsError(f"manifest already exists: {manifest_path}. Pass --overwrite-manifest to rewrite it.")

    session_filters = {_slugify(item) for item in (args.session_filter or []) if str(item).strip()} or None
    capture_type_filters = _normalize_capture_type_filters(args.capture_type_filter)
    state = _load_state(state_path, reset=args.reset_state)
    imported_keys = set(state.get("imported_metadata_paths", []))

    discovered = _discover_capture_records(
        capture_root,
        session_filters=session_filters,
        capture_type_filters=capture_type_filters,
    )

    if args.limit is not None:
        discovered = discovered[: max(0, args.limit)]

    imported_now = 0
    for record in discovered:
        source_key = record["relative_metadata_path"].as_posix()
        destination_image = output_root / "raw" / record["relative_image_path"]
        destination_metadata = output_root / "raw" / record["relative_metadata_path"]
        if source_key in imported_keys and destination_image.exists() and destination_metadata.exists():
            continue
        _copy_or_link(record["source_image_path"], destination_image, copy_mode=args.copy_mode)
        _copy_or_link(record["source_metadata_path"], destination_metadata, copy_mode=args.copy_mode)
        imported_keys.add(source_key)
        imported_now += 1

    imported_images = sorted((output_root / "raw").rglob("*")) if (output_root / "raw").exists() else []
    imported_metadata_paths = [
        path for path in imported_images if path.is_file() and path.suffix.lower() == ".json" and path.name.lower() != "captures.jsonl"
    ]

    assets: list[DatasetAssetRecord] = []
    source_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    collection_times: list[str] = []

    for metadata_file in imported_metadata_paths:
        payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        image_filename = str(payload.get("imageFilename") or "").strip()
        image_file = metadata_file.with_suffix(".jpg")
        if image_filename:
            candidate = metadata_file.parent / image_filename
            if candidate.exists():
                image_file = candidate
        if not image_file.exists():
            continue

        relative_image_path = image_file.relative_to(output_root).as_posix()
        relative_metadata_path = metadata_file.relative_to(output_root).as_posix()
        capture_type = _slugify(payload.get("captureType"))
        asset_id = _build_asset_id(image_file.relative_to(output_root / "raw"), payload)
        session_id = _slugify(payload.get("sessionId"))
        timestamp_utc = str(payload.get("timestampUtc") or "")
        if timestamp_utc:
            collection_times.append(timestamp_utc)

        asset = DatasetAssetRecord(
            asset_id=asset_id,
            relative_path=relative_image_path,
            capture_session_id=session_id,
            timestamp_utc=timestamp_utc or None,
            lighting_conditions=[LightingCondition.unknown],
            annotations=[],
            tags=_build_tags(payload, capture_type=capture_type),
        )
        assets.append(asset)

        source_row = {
            "asset_id": asset.asset_id,
            "capture_session_id": asset.capture_session_id,
            "relative_path": asset.relative_path,
            "metadata_relative_path": relative_metadata_path,
            "source_capture_id": str(payload.get("captureId") or ""),
            "capture_type": capture_type,
            "timestamp_utc": timestamp_utc,
            "device_label": str(payload.get("deviceLabel") or ""),
            "remote_address": str(payload.get("remoteAddress") or ""),
            "gps": payload.get("gps"),
            "heading_degrees": payload.get("headingDegrees"),
            "speed_mps": payload.get("speedMps"),
        }
        source_rows.append(source_row)
        review_rows.append(_build_review_row(source_row, payload, metadata_relative_path=relative_metadata_path))

    if not assets:
        print("No imported mobile captures were found after filtering.")
        return 0

    provenance = DatasetProvenance(
        source_name="RepoScan mobile capture intake",
        source_kind=DatasetSourceKind.field_capture,
        license_tier=DatasetLicenseTier.internal,
        license_name="internal field capture",
        license_reference=str(capture_root),
        region="us-ok",
        collected_by="mobile_pwa_capture",
        collection_start_utc=min(collection_times) if collection_times else None,
        collection_end_utc=max(collection_times) if collection_times else None,
        notes="Foreground mobile PWA captures uploaded directly to the RepoScan ingest workstation and imported for review.",
    )

    manifest = TrainingDatasetManifest(
        dataset_name=args.dataset_name,
        dataset_version=str(args.dataset_version),
        task=DatasetTask(args.task),
        format=DatasetFormat.generic_capture,
        storage_root=str(output_root),
        review_status=DatasetReviewStatus.pending,
        provenance=provenance,
        assets=assets,
        notes="Pending mobile-capture intake. Review and promote before training use.",
    )

    output_root.mkdir(parents=True, exist_ok=True)
    _write_yaml(manifest_path, manifest.model_dump(mode="json", exclude_none=True))
    _write_jsonl(output_root / "metadata" / "source_records.jsonl", source_rows)
    _write_csv(review_csv, review_rows, REVIEW_INDEX_FIELDNAMES)

    state["imported_metadata_paths"] = sorted(imported_keys)
    _save_state(state_path, state)

    print(
        json.dumps(
            {
                "capture_root": str(capture_root),
                "output_root": str(output_root),
                "manifest_path": str(manifest_path),
                "review_csv": str(review_csv),
                "assets": len(assets),
                "imported_now": imported_now,
                "state_path": str(state_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

