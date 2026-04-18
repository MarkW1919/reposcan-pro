from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


DETECTION_REVIEW_FIELDNAMES = [
    "asset_id",
    "capture_session_id",
    "frame_relative_path",
    "metadata_relative_path",
    "timestamp_utc",
    "detection_kind",
    "detection_index",
    "vehicle_index",
    "crop_relative_path",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "confidence",
    "class_label",
    "ocr_text",
    "ocr_confidence",
    "suggested_color",
    "suggested_color_confidence",
    "suggested_make",
    "suggested_make_confidence",
    "suggested_model",
    "suggested_model_confidence",
    "suggested_year",
    "suggested_year_confidence",
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

FRAME_SUMMARY_FIELDNAMES = [
    "asset_id",
    "capture_session_id",
    "frame_relative_path",
    "metadata_relative_path",
    "timestamp_utc",
    "frame_width",
    "frame_height",
    "vehicle_detection_count",
    "plate_detection_count",
    "ocr_candidate_count",
    "attribute_prediction_count",
    "processing_latency_ms",
    "preprocessing_artifact_generated",
    "prepared_frame_relative_path",
]


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "alerting" / "src",
        repo_root / "services" / "capture" / "src",
        repo_root / "services" / "inference" / "src",
        repo_root / "services" / "preprocessing" / "src",
        repo_root / "services" / "storage" / "src",
        repo_root / "services" / "tracking" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run batch inference over a generic-capture manifest and emit a detection review queue."
    )
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-csv")
    parser.add_argument("--frame-summary-csv")
    parser.add_argument("--candidates-jsonl")
    parser.add_argument("--model-config", default="configs/models/local-onnx-runtime.yaml")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--detection-kind", choices=("vehicle", "plate", "both"), default="both")
    parser.add_argument("--min-vehicle-confidence", type=float)
    parser.add_argument("--min-plate-confidence", type=float)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--disable-preprocessing", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _resolve_path(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _resolve_storage_root(repo_root: Path, storage_root: str) -> Path:
    root = Path(storage_root)
    if root.is_absolute():
        return root.resolve()
    return (repo_root / root).resolve()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _normalize_detection_kind(value: str) -> set[str]:
    if value == "both":
        return {"vehicle", "plate"}
    return {value}


def _default_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = [character if character.isalnum() else "_" for character in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or "unknown"


def _load_sidecar_metadata(image_path: Path) -> tuple[Path | None, dict[str, Any]]:
    metadata_path = image_path.with_suffix(".json")
    if not metadata_path.exists():
        return None, {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return metadata_path, {}
    if not isinstance(payload, dict):
        return metadata_path, {}
    return metadata_path, payload


def _gps_snapshot_from_payload(payload: dict[str, Any]):
    gps = payload.get("gps")
    if not isinstance(gps, dict):
        return None
    latitude = gps.get("latitude")
    longitude = gps.get("longitude")
    if latitude is None or longitude is None:
        return None

    from reposcan_contracts.frame import GpsSnapshot

    return GpsSnapshot(
        latitude=float(latitude),
        longitude=float(longitude),
        accuracy_m=(float(gps["accuracyMeters"]) if gps.get("accuracyMeters") is not None else None),
        altitude_m=(float(gps["altitudeMeters"]) if gps.get("altitudeMeters") is not None else None),
    )


def _open_image(path: Path) -> tuple[Image.Image, int, int]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        return rgb, width, height


def _crop_to_file(image: Image.Image, bbox, destination: Path) -> None:
    left = max(0, int(bbox.x))
    top = max(0, int(bbox.y))
    right = min(image.width, int(bbox.x + bbox.w))
    bottom = min(image.height, int(bbox.y + bbox.h))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if right <= left or bottom <= top:
        Image.new("RGB", (max(int(bbox.w), 1), max(int(bbox.h), 1)), color=(0, 0, 0)).save(destination)
        return
    image.crop((left, top, right, bottom)).save(destination)


def _ensure_generic_capture_manifest(manifest) -> None:
    from reposcan_contracts.dataset import DatasetFormat

    if manifest.format != DatasetFormat.generic_capture:
        raise ValueError("capture detection suggestions require a dataset manifest with format=generic_capture")
    if not manifest.assets:
        raise ValueError("capture detection suggestions require asset-level records in the source manifest")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest
    from reposcan_contracts.dataset import DatasetReviewStatus
    from reposcan_contracts.frame import CameraProfile, FrameEnvelope, PreparedFrame, SourceType
    from reposcan_inference.service import InferenceService
    from reposcan_preprocessing import PreprocessingService

    args = parse_args()
    dataset_manifest_path = _resolve_path(repo_root, args.dataset_manifest)
    output_root = _resolve_path(repo_root, args.output_root)
    output_csv = _resolve_path(repo_root, args.output_csv) if args.output_csv else output_root / "metadata" / "detection_review.csv"
    frame_summary_csv = (
        _resolve_path(repo_root, args.frame_summary_csv)
        if args.frame_summary_csv
        else output_root / "metadata" / "frame_summary.csv"
    )
    candidates_jsonl = (
        _resolve_path(repo_root, args.candidates_jsonl)
        if args.candidates_jsonl
        else output_root / "metadata" / "inference_candidates.jsonl"
    )
    model_config_path = _resolve_path(repo_root, args.model_config)
    pipeline_config_path = _resolve_path(repo_root, args.pipeline_config)

    manifest = load_training_dataset_manifest(dataset_manifest_path)
    _ensure_generic_capture_manifest(manifest)
    if manifest.review_status == DatasetReviewStatus.quarantined:
        raise ValueError(f"dataset manifest '{manifest.dataset_name}' is quarantined")

    if output_root.exists():
        if not args.overwrite:
            raise FileExistsError(f"output root already exists: {output_root}. Pass --overwrite to regenerate it.")
        shutil.rmtree(output_root)

    storage_root = _resolve_storage_root(repo_root, manifest.storage_root)
    output_root.mkdir(parents=True, exist_ok=True)

    preprocessing_service = None
    if not args.disable_preprocessing:
        preprocessing_service = PreprocessingService.from_config_path(
            str(pipeline_config_path),
            artifact_root=output_root / "preprocessed",
        )

    inference_service = InferenceService.from_config_paths(
        model_config_path=str(model_config_path),
        pipeline_config_path=str(pipeline_config_path),
    )

    requested_kinds = _normalize_detection_kind(args.detection_kind)
    min_vehicle_confidence = args.min_vehicle_confidence
    min_plate_confidence = args.min_plate_confidence

    detection_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    assets = list(manifest.assets)
    if args.limit is not None:
        assets = assets[: max(args.limit, 0)]

    for frame_number, asset in enumerate(assets):
        image_path = storage_root / asset.relative_path
        if not image_path.exists():
            raise FileNotFoundError(f"missing capture image for asset '{asset.asset_id}': {image_path}")

        image, width, height = _open_image(image_path)
        metadata_path, metadata_payload = _load_sidecar_metadata(image_path)
        gps_snapshot = _gps_snapshot_from_payload(metadata_payload)
        timestamp_utc = asset.timestamp_utc or str(metadata_payload.get("timestampUtc") or _default_timestamp())
        device_label = str(metadata_payload.get("deviceLabel") or "")
        camera_id = _slugify(device_label) if device_label else "mobile_capture_import"

        frame = FrameEnvelope(
            frame_id=asset.asset_id,
            camera_id=camera_id,
            timestamp_utc=timestamp_utc,
            frame_path=str(image_path),
            frame_number=frame_number,
            source_type=SourceType.file,
            camera_profile=CameraProfile(
                camera_id=camera_id,
                display_name=device_label or None,
                source_type=SourceType.file,
                resolution_w=width,
                resolution_h=height,
                gps_latitude=(gps_snapshot.latitude if gps_snapshot else None),
                gps_longitude=(gps_snapshot.longitude if gps_snapshot else None),
            ),
            gps_snapshot=gps_snapshot,
            sequence_id=asset.capture_session_id,
        )

        prepared_frame: FrameEnvelope | PreparedFrame = frame
        if preprocessing_service is not None:
            prepared_frame = preprocessing_service.prepare(frame)

        candidate = inference_service.run(prepared_frame)
        candidate_rows.append(candidate.model_dump(mode="json"))

        prepared_relative_path = ""
        if isinstance(prepared_frame, PreparedFrame):
            try:
                prepared_relative_path = Path(prepared_frame.prepared_frame_path).relative_to(output_root).as_posix()
            except ValueError:
                prepared_relative_path = prepared_frame.prepared_frame_path

        metadata_relative_path = ""
        if metadata_path is not None:
            metadata_relative_path = metadata_path.relative_to(storage_root).as_posix()

        summary_rows.append(
            {
                "asset_id": asset.asset_id,
                "capture_session_id": asset.capture_session_id,
                "frame_relative_path": asset.relative_path,
                "metadata_relative_path": metadata_relative_path,
                "timestamp_utc": timestamp_utc,
                "frame_width": width,
                "frame_height": height,
                "vehicle_detection_count": len(candidate.vehicle_detections),
                "plate_detection_count": len(candidate.plate_detections),
                "ocr_candidate_count": len(candidate.ocr_candidates),
                "attribute_prediction_count": len(candidate.attribute_predictions),
                "processing_latency_ms": round(candidate.processing_latency_ms, 3),
                "preprocessing_artifact_generated": (
                    "true"
                    if preprocessing_service is not None and prepared_relative_path
                    else "false"
                ),
                "prepared_frame_relative_path": prepared_relative_path,
            }
        )

        if "vehicle" in requested_kinds:
            for detection_index, detection in enumerate(candidate.vehicle_detections):
                if min_vehicle_confidence is not None and detection.confidence < min_vehicle_confidence:
                    continue
                crop_relative_path = (
                    Path("crops")
                    / "vehicle"
                    / asset.capture_session_id
                    / f"{asset.asset_id}_vehicle_{detection_index:03d}.jpg"
                )
                crop_path = output_root / crop_relative_path
                _crop_to_file(image, detection.bbox, crop_path)

                attributes = (
                    candidate.attribute_predictions[detection_index]
                    if detection_index < len(candidate.attribute_predictions)
                    else None
                )

                detection_rows.append(
                    {
                        "asset_id": asset.asset_id,
                        "capture_session_id": asset.capture_session_id,
                        "frame_relative_path": asset.relative_path,
                        "metadata_relative_path": metadata_relative_path,
                        "timestamp_utc": timestamp_utc,
                        "detection_kind": "vehicle",
                        "detection_index": detection_index,
                        "vehicle_index": detection_index,
                        "crop_relative_path": crop_relative_path.as_posix(),
                        "bbox_x": detection.bbox.x,
                        "bbox_y": detection.bbox.y,
                        "bbox_w": detection.bbox.w,
                        "bbox_h": detection.bbox.h,
                        "confidence": round(detection.confidence, 6),
                        "class_label": detection.class_label,
                        "ocr_text": "",
                        "ocr_confidence": "",
                        "suggested_color": attributes.color if attributes is not None else "",
                        "suggested_color_confidence": (
                            round(attributes.color_confidence, 6)
                            if attributes is not None and attributes.color_confidence is not None
                            else ""
                        ),
                        "suggested_make": attributes.make if attributes is not None else "",
                        "suggested_make_confidence": (
                            round(attributes.make_confidence, 6)
                            if attributes is not None and attributes.make_confidence is not None
                            else ""
                        ),
                        "suggested_model": attributes.model_label if attributes is not None else "",
                        "suggested_model_confidence": (
                            round(attributes.model_confidence, 6)
                            if attributes is not None and attributes.model_confidence is not None
                            else ""
                        ),
                        "suggested_year": attributes.year if attributes is not None else "",
                        "suggested_year_confidence": (
                            round(attributes.year_confidence, 6)
                            if attributes is not None and attributes.year_confidence is not None
                            else ""
                        ),
                        "device_label": device_label,
                        "remote_address": str(metadata_payload.get("remoteAddress") or ""),
                        "gps_latitude": metadata_payload.get("gps", {}).get("latitude", "")
                        if isinstance(metadata_payload.get("gps"), dict)
                        else "",
                        "gps_longitude": metadata_payload.get("gps", {}).get("longitude", "")
                        if isinstance(metadata_payload.get("gps"), dict)
                        else "",
                        "gps_accuracy_meters": metadata_payload.get("gps", {}).get("accuracyMeters", "")
                        if isinstance(metadata_payload.get("gps"), dict)
                        else "",
                        "heading_degrees": metadata_payload.get("headingDegrees", ""),
                        "speed_mps": metadata_payload.get("speedMps", ""),
                        "reposcan_reviewed": "false",
                        "reposcan_accepted": "false",
                        "reviewer_notes": "",
                    }
                )

        if "plate" in requested_kinds:
            for detection_index, detection in enumerate(candidate.plate_detections):
                if min_plate_confidence is not None and detection.confidence < min_plate_confidence:
                    continue
                crop_relative_path = (
                    Path("crops")
                    / "plate"
                    / asset.capture_session_id
                    / f"{asset.asset_id}_plate_{detection_index:03d}.jpg"
                )
                crop_path = output_root / crop_relative_path
                _crop_to_file(image, detection.bbox, crop_path)

                ocr_candidate = None
                if detection_index < len(candidate.ocr_candidates):
                    ocr_candidate = candidate.ocr_candidates[detection_index]
                elif len(candidate.ocr_candidates) == 1:
                    ocr_candidate = candidate.ocr_candidates[0]

                detection_rows.append(
                    {
                        "asset_id": asset.asset_id,
                        "capture_session_id": asset.capture_session_id,
                        "frame_relative_path": asset.relative_path,
                        "metadata_relative_path": metadata_relative_path,
                        "timestamp_utc": timestamp_utc,
                        "detection_kind": "plate",
                        "detection_index": detection_index,
                        "vehicle_index": detection.vehicle_index if detection.vehicle_index is not None else "",
                        "crop_relative_path": crop_relative_path.as_posix(),
                        "bbox_x": detection.bbox.x,
                        "bbox_y": detection.bbox.y,
                        "bbox_w": detection.bbox.w,
                        "bbox_h": detection.bbox.h,
                        "confidence": round(detection.confidence, 6),
                        "class_label": "plate",
                        "ocr_text": ocr_candidate.text if ocr_candidate is not None else "",
                        "ocr_confidence": (
                            round(ocr_candidate.confidence, 6)
                            if ocr_candidate is not None
                            else ""
                        ),
                        "suggested_color": "",
                        "suggested_color_confidence": "",
                        "suggested_make": "",
                        "suggested_make_confidence": "",
                        "suggested_model": "",
                        "suggested_model_confidence": "",
                        "suggested_year": "",
                        "suggested_year_confidence": "",
                        "device_label": device_label,
                        "remote_address": str(metadata_payload.get("remoteAddress") or ""),
                        "gps_latitude": metadata_payload.get("gps", {}).get("latitude", "")
                        if isinstance(metadata_payload.get("gps"), dict)
                        else "",
                        "gps_longitude": metadata_payload.get("gps", {}).get("longitude", "")
                        if isinstance(metadata_payload.get("gps"), dict)
                        else "",
                        "gps_accuracy_meters": metadata_payload.get("gps", {}).get("accuracyMeters", "")
                        if isinstance(metadata_payload.get("gps"), dict)
                        else "",
                        "heading_degrees": metadata_payload.get("headingDegrees", ""),
                        "speed_mps": metadata_payload.get("speedMps", ""),
                        "reposcan_reviewed": "false",
                        "reposcan_accepted": "false",
                        "reviewer_notes": "",
                    }
                )

        image.close()

    _write_csv(output_csv, detection_rows, DETECTION_REVIEW_FIELDNAMES)
    _write_csv(frame_summary_csv, summary_rows, FRAME_SUMMARY_FIELDNAMES)
    _write_jsonl(candidates_jsonl, candidate_rows)

    print(
        json.dumps(
            {
                "dataset_manifest": str(dataset_manifest_path),
                "output_root": str(output_root),
                "output_csv": str(output_csv),
                "frame_summary_csv": str(frame_summary_csv),
                "candidates_jsonl": str(candidates_jsonl),
                "frames_processed": len(summary_rows),
                "detection_rows": len(detection_rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
