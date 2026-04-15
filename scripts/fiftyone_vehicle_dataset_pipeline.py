from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def _require_fiftyone():
    try:
        import fiftyone as fo
        import fiftyone.zoo as foz
    except ImportError as exc:
        raise RuntimeError(
            "FiftyOne is required for this pipeline. Install it with "
            "`python -m pip install fiftyone` or `python -m pip install \".[dataset]\"`."
        ) from exc
    return fo, foz


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package-backed vehicle image intake and RepoScan dataset export using FiftyOne."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pull = subparsers.add_parser("pull-open-images", help="Pull Open Images samples into a FiftyOne dataset.")
    pull.add_argument("--dataset-name", default="reposcan-open-images-vehicle-candidates")
    pull.add_argument("--split", default="validation", choices=["train", "validation", "test"])
    pull.add_argument(
        "--classes",
        nargs="+",
        default=["Car", "Truck", "Bus"],
        help="Open Images classes to pull. Start with broad vehicle classes, then review in FiftyOne.",
    )
    pull.add_argument("--max-samples", type=int, default=200)
    pull.add_argument("--label-types", nargs="+", default=["detections"])
    pull.add_argument("--zoo-dir", help="Optional FiftyOne dataset zoo cache directory.")
    pull.add_argument("--non-persistent", action="store_true", help="Do not persist the FiftyOne dataset after import.")
    pull.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete and recreate the target FiftyOne dataset before pulling. Existing review fields will be lost.",
    )
    pull.add_argument("--launch-app", action="store_true")
    pull.add_argument("--port", type=int, default=5151)

    launch = subparsers.add_parser("launch-app", help="Open the FiftyOne app for a dataset.")
    launch.add_argument("--dataset-name", required=True)
    launch.add_argument("--port", type=int, default=5151)

    template = subparsers.add_parser("write-review-template", help="Write a CSV template for batch review labels.")
    template.add_argument("--dataset-name", required=True)
    template.add_argument("--output-csv", required=True)

    apply_review = subparsers.add_parser("apply-review-csv", help="Apply reviewed vehicle labels from a CSV file.")
    apply_review.add_argument("--dataset-name", required=True)
    apply_review.add_argument("--review-csv", required=True)
    apply_review.add_argument("--key-field", choices=["sample_id", "filepath", "filename"], default="sample_id")
    apply_review.add_argument("--strict", action="store_true", help="Fail when a CSV row does not match a sample.")

    crop_review = subparsers.add_parser(
        "export-attribute-crop-review",
        help="Export detected vehicle crops and a CSV queue for make/model/year/color review.",
    )
    crop_review.add_argument("--dataset-name", required=True)
    crop_review.add_argument("--output-root", required=True)
    crop_review.add_argument("--review-csv", required=True)
    crop_review.add_argument("--detections-field", default="ground_truth")
    crop_review.add_argument("--source-labels", nargs="+", default=["Car", "Truck", "Bus", "Motorcycle", "Van", "Taxi"])
    crop_review.add_argument("--padding-ratio", type=float, default=0.05)
    crop_review.add_argument("--min-width-px", type=int, default=48)
    crop_review.add_argument("--min-height-px", type=int, default=48)
    crop_review.add_argument("--max-crops", type=int)
    crop_review.add_argument("--overwrite", action="store_true", help="Replace a non-empty crop output root before export.")

    crop_export = subparsers.add_parser(
        "export-reviewed-crops",
        help="Export reviewed attribute crop CSV rows to a RepoScan ImageFolder manifest.",
    )
    crop_export.add_argument("--review-csv", required=True)
    crop_export.add_argument("--output-root", required=True)
    crop_export.add_argument("--manifest-path", required=True)
    crop_export.add_argument("--dataset-name", required=True)
    crop_export.add_argument("--dataset-version", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    crop_export.add_argument(
        "--task",
        choices=["vehicle_make_model_classification", "vehicle_color_classification", "vehicle_year_classification"],
        default="vehicle_make_model_classification",
    )
    crop_export.add_argument("--seed", type=int, default=42)
    crop_export.add_argument("--train-ratio", type=float, default=0.8)
    crop_export.add_argument("--validation-ratio", type=float, default=0.1)
    crop_export.add_argument("--holdout-ratio", type=float, default=0.1)
    crop_export.add_argument("--copy-mode", choices=["copy", "hardlink"], default="copy")
    crop_export.add_argument("--reviewer", default="attribute_crop_reviewer")
    crop_export.add_argument("--review-status", choices=["pending", "approved"], default="approved")
    crop_export.add_argument("--allow-unreviewed", action="store_true")
    crop_export.add_argument("--overwrite", action="store_true", help="Replace a non-empty output root before export.")

    export = subparsers.add_parser("export-reviewed", help="Export approved FiftyOne samples to RepoScan ImageFolder.")
    export.add_argument("--dataset-name", required=True)
    export.add_argument("--output-root", required=True)
    export.add_argument("--manifest-path", required=True)
    export.add_argument("--dataset-version", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    export.add_argument(
        "--task",
        choices=["vehicle_make_model_classification", "vehicle_color_classification", "vehicle_year_classification"],
        default="vehicle_make_model_classification",
    )
    export.add_argument("--class-field", default="reposcan_class_label")
    export.add_argument("--accepted-field", default="reposcan_accepted")
    export.add_argument("--reviewed-field", default="reposcan_reviewed")
    export.add_argument("--allow-unreviewed", action="store_true")
    export.add_argument("--seed", type=int, default=42)
    export.add_argument("--train-ratio", type=float, default=0.8)
    export.add_argument("--validation-ratio", type=float, default=0.1)
    export.add_argument("--holdout-ratio", type=float, default=0.1)
    export.add_argument("--copy-mode", choices=["copy", "hardlink"], default="copy")
    export.add_argument("--reviewer", default="fiftyone_vehicle_reviewer")
    export.add_argument("--review-status", choices=["pending", "approved"], default="approved")
    export.add_argument("--overwrite", action="store_true", help="Replace a non-empty output root before export.")

    yolo = subparsers.add_parser("export-detections-yolo", help="Export FiftyOne detections to RepoScan YOLO format.")
    yolo.add_argument("--dataset-name", required=True)
    yolo.add_argument("--output-root", required=True)
    yolo.add_argument("--manifest-path", required=True)
    yolo.add_argument("--dataset-version", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    yolo.add_argument("--detections-field", default="ground_truth")
    yolo.add_argument("--source-labels", nargs="+", default=["Car", "Truck", "Bus", "Motorcycle", "Van", "Taxi"])
    yolo.add_argument("--target-class-name", default="vehicle")
    yolo.add_argument("--accepted-field", default="reposcan_accepted")
    yolo.add_argument("--reviewed-field", default="reposcan_reviewed")
    yolo.add_argument("--require-reviewed", action="store_true")
    yolo.add_argument("--seed", type=int, default=42)
    yolo.add_argument("--train-ratio", type=float, default=0.8)
    yolo.add_argument("--validation-ratio", type=float, default=0.1)
    yolo.add_argument("--holdout-ratio", type=float, default=0.1)
    yolo.add_argument("--copy-mode", choices=["copy", "hardlink"], default="copy")
    yolo.add_argument("--reviewer", default="open_images_detection_export")
    yolo.add_argument("--review-status", choices=["pending", "approved"], default="pending")
    yolo.add_argument("--overwrite", action="store_true", help="Replace a non-empty output root before export.")
    return parser.parse_args()


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = [character if character.isalnum() else "_" for character in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or "unknown"


def _sample_field(sample, field_name: str, default: Any = None) -> Any:
    try:
        value = sample.get_field(field_name)
    except Exception:
        return default
    return default if value is None else value


def _exact_sample_count(dataset) -> int:
    try:
        return int(dataset._sample_collection.count_documents({}))
    except Exception:
        return sum(1 for _ in dataset)


def _load_open_images_zoo_dataset(foz, args: argparse.Namespace, *, dataset_name: str):
    return foz.load_zoo_dataset(
        "open-images-v7",
        split=args.split,
        label_types=args.label_types,
        classes=args.classes,
        only_matching=True,
        max_samples=args.max_samples,
        dataset_name=dataset_name,
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "accepted", "approved"}


def _split_tag_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    for separator in ("|", ";"):
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _copy_or_link(source: Path, destination: Path, *, copy_mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    if copy_mode == "hardlink":
        try:
            destination.hardlink_to(source)
            return
        except OSError:
            pass
    shutil.copy2(source, destination)


def _prepare_export_root(output_root: Path, *, overwrite: bool) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"output root is not empty: {output_root}. Pass --overwrite to replace it.")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)


def pull_open_images(args: argparse.Namespace) -> int:
    fo, foz = _require_fiftyone()
    if args.zoo_dir:
        fo.config.dataset_zoo_dir = str(Path(args.zoo_dir).resolve())

    if args.replace_existing and fo.dataset_exists(args.dataset_name):
        fo.delete_dataset(args.dataset_name)
        print(f"Deleted existing FiftyOne dataset: {args.dataset_name}")

    if fo.dataset_exists(args.dataset_name):
        dataset = fo.load_dataset(args.dataset_name)
        before_count = _exact_sample_count(dataset)
        print(f"Using existing FiftyOne dataset: {dataset.name} ({before_count} samples)")
        if before_count < args.max_samples:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            temp_name = f"{args.dataset_name}_pull_{stamp}"
            if fo.dataset_exists(temp_name):
                fo.delete_dataset(temp_name)
            temp_dataset = None
            try:
                temp_dataset = _load_open_images_zoo_dataset(foz, args, dataset_name=temp_name)
                temp_count = _exact_sample_count(temp_dataset)
                dataset.merge_samples(
                    temp_dataset,
                    key_field="filepath",
                    skip_existing=True,
                    insert_new=True,
                    overwrite=False,
                    include_info=False,
                )
                after_count = _exact_sample_count(dataset)
                print(
                    "Merged Open Images pull: "
                    f"temp_samples={temp_count}, added={after_count - before_count}, total={after_count}"
                )
            finally:
                if temp_dataset is not None and fo.dataset_exists(temp_name):
                    fo.delete_dataset(temp_name)
        else:
            print(
                "Existing dataset already meets or exceeds requested max_samples. "
                "Increase --max-samples or pass --replace-existing to pull a different candidate pool."
            )
    else:
        dataset = _load_open_images_zoo_dataset(foz, args, dataset_name=args.dataset_name)
        print(f"Created FiftyOne dataset: {dataset.name} ({_exact_sample_count(dataset)} samples)")

    dataset.persistent = not args.non_persistent
    dataset.info["reposcan_source"] = {
        "source": "open-images-v7",
        "split": args.split,
        "classes": args.classes,
        "pulled_at_utc": _utcnow(),
        "review_fields": {
            "reposcan_accepted": "set true after visual/license/label review",
            "reposcan_reviewed": "set true after human review",
            "reposcan_class_label": "ImageFolder class, e.g. chevrolet_silverado or ford_f_series",
            "reposcan_vehicle_make": "required for make/model training",
            "reposcan_vehicle_model": "required for make/model training",
            "reposcan_vehicle_year": "optional year/generation support",
            "reposcan_vehicle_color": "required for color training",
            "reposcan_oklahoma_tags": "list such as vehicle_class:pickup, make_model:chevrolet_silverado",
        },
    }

    for sample in dataset:
        if _sample_field(sample, "reposcan_accepted") is None:
            sample["reposcan_accepted"] = False
        if _sample_field(sample, "reposcan_reviewed") is None:
            sample["reposcan_reviewed"] = False
        for field_name in (
            "reposcan_class_label",
            "reposcan_vehicle_make",
            "reposcan_vehicle_model",
            "reposcan_vehicle_year",
            "reposcan_vehicle_color",
        ):
            if _sample_field(sample, field_name) is None:
                sample[field_name] = ""
        if _sample_field(sample, "reposcan_oklahoma_tags") is None:
            sample["reposcan_oklahoma_tags"] = []
        if "reposcan_candidate" not in sample.tags:
            sample.tags.append("reposcan_candidate")
        sample.save()

    dataset.save()
    print("Review in FiftyOne, then set reposcan_accepted=true, reposcan_reviewed=true, and class/vehicle fields.")
    print(f"Launch command: .\\.venv\\Scripts\\python.exe .\\scripts\\fiftyone_vehicle_dataset_pipeline.py launch-app --dataset-name {dataset.name}")

    if args.launch_app:
        session = fo.launch_app(dataset, port=args.port)
        session.wait()
    return 0


def write_review_template(args: argparse.Namespace) -> int:
    fo, _ = _require_fiftyone()
    dataset = fo.load_dataset(args.dataset_name)
    output_csv = Path(args.output_csv).resolve()
    fieldnames = [
        "sample_id",
        "filepath",
        "filename",
        "candidate_tags",
        "reposcan_accepted",
        "reposcan_reviewed",
        "reposcan_class_label",
        "reposcan_vehicle_make",
        "reposcan_vehicle_model",
        "reposcan_vehicle_year",
        "reposcan_vehicle_color",
        "reposcan_oklahoma_tags",
        "reviewer_notes",
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for sample in dataset:
            writer.writerow(
                {
                    "sample_id": sample.id,
                    "filepath": sample.filepath,
                    "filename": Path(sample.filepath).name,
                    "candidate_tags": "|".join(sample.tags or []),
                    "reposcan_accepted": _sample_field(sample, "reposcan_accepted", False),
                    "reposcan_reviewed": _sample_field(sample, "reposcan_reviewed", False),
                    "reposcan_class_label": _sample_field(sample, "reposcan_class_label", ""),
                    "reposcan_vehicle_make": _sample_field(sample, "reposcan_vehicle_make", ""),
                    "reposcan_vehicle_model": _sample_field(sample, "reposcan_vehicle_model", ""),
                    "reposcan_vehicle_year": _sample_field(sample, "reposcan_vehicle_year", ""),
                    "reposcan_vehicle_color": _sample_field(sample, "reposcan_vehicle_color", ""),
                    "reposcan_oklahoma_tags": "|".join(_sample_field(sample, "reposcan_oklahoma_tags", []) or []),
                    "reviewer_notes": "",
                }
            )
    print(f"Wrote review template for {_exact_sample_count(dataset)} samples: {output_csv}")
    return 0


def apply_review_csv(args: argparse.Namespace) -> int:
    fo, _ = _require_fiftyone()
    dataset = fo.load_dataset(args.dataset_name)
    review_csv = Path(args.review_csv).resolve()
    with review_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    sample_index: dict[str, Any] = {}
    for sample in dataset:
        if args.key_field == "sample_id":
            key = sample.id
        elif args.key_field == "filename":
            key = Path(sample.filepath).name
        else:
            key = str(Path(sample.filepath).resolve()).lower()
        sample_index[key] = sample

    updated = 0
    missing: list[str] = []
    review_fields = [
        "reposcan_accepted",
        "reposcan_reviewed",
        "reposcan_class_label",
        "reposcan_vehicle_make",
        "reposcan_vehicle_model",
        "reposcan_vehicle_year",
        "reposcan_vehicle_color",
    ]
    for row in rows:
        raw_key = str(row.get(args.key_field, "") or "").strip()
        key = str(Path(raw_key).resolve()).lower() if args.key_field == "filepath" else raw_key
        sample = sample_index.get(key)
        if sample is None:
            missing.append(raw_key)
            continue

        for field_name in review_fields:
            if field_name not in row or row[field_name] is None:
                continue
            value = row[field_name].strip()
            if field_name in {"reposcan_accepted", "reposcan_reviewed"}:
                sample[field_name] = _truthy(value)
            elif value:
                sample[field_name] = value

        if "reposcan_oklahoma_tags" in row:
            review_tags = _split_tag_text(row.get("reposcan_oklahoma_tags"))
            sample["reposcan_oklahoma_tags"] = review_tags
            for tag in review_tags:
                if tag not in sample.tags:
                    sample.tags.append(tag)
        sample.save()
        updated += 1

    if missing:
        message = f"{len(missing)} CSV rows did not match samples using {args.key_field}"
        if args.strict:
            raise ValueError(f"{message}: {missing[:5]}")
        print(f"WARNING: {message}; first missing keys: {missing[:5]}", file=sys.stderr)

    dataset.save()
    print(f"Applied review rows: {updated}")
    return 0


def launch_app(args: argparse.Namespace) -> int:
    fo, _ = _require_fiftyone()
    dataset = fo.load_dataset(args.dataset_name)
    print(f"Launching FiftyOne app for {dataset.name} on port {args.port}")
    session = fo.launch_app(dataset, port=args.port)
    session.wait()
    return 0


def _split_samples(samples: list[Any], *, train_ratio: float, validation_ratio: float, holdout_ratio: float, seed: int) -> dict[str, list[Any]]:
    ratio_total = train_ratio + validation_ratio + holdout_ratio
    if abs(ratio_total - 1.0) > 1e-6:
        raise ValueError("train, validation, and holdout ratios must add up to 1.0")

    grouped: dict[str, list[Any]] = {}
    for sample in samples:
        label = _slugify(_sample_field(sample, "reposcan_export_class"))
        grouped.setdefault(label, []).append(sample)

    randomizer = random.Random(seed)
    split_map = {"train": [], "validation": [], "holdout": []}
    for class_samples in grouped.values():
        shuffled = list(class_samples)
        randomizer.shuffle(shuffled)
        count = len(shuffled)
        if count >= 10:
            validation_count = max(1, int(round(count * validation_ratio)))
            holdout_count = max(1, int(round(count * holdout_ratio)))
        elif count >= 3:
            validation_count = 1
            holdout_count = 1
        elif count == 2:
            validation_count = 1
            holdout_count = 0
        else:
            validation_count = 0
            holdout_count = 0
        if validation_count + holdout_count >= count:
            holdout_count = max(0, count - validation_count - 1)
        train_count = count - validation_count - holdout_count
        split_map["train"].extend(shuffled[:train_count])
        split_map["validation"].extend(shuffled[train_count : train_count + validation_count])
        split_map["holdout"].extend(shuffled[train_count + validation_count :])
    return split_map


def _annotation_tasks_for_task(task: str):
    from reposcan_contracts.dataset import AnnotationTask

    if task == "vehicle_color_classification":
        return [AnnotationTask.vehicle_color]
    if task == "vehicle_year_classification":
        return [AnnotationTask.vehicle_year]
    return [AnnotationTask.vehicle_make, AnnotationTask.vehicle_model]


def _validate_label_fields(sample, *, task: str, class_label: str) -> tuple[str | None, str | None, str | None, str | None]:
    make = str(_sample_field(sample, "reposcan_vehicle_make", "") or "").strip()
    model = str(_sample_field(sample, "reposcan_vehicle_model", "") or "").strip()
    year = str(_sample_field(sample, "reposcan_vehicle_year", "") or "").strip()
    color = str(_sample_field(sample, "reposcan_vehicle_color", "") or "").strip()

    if task == "vehicle_make_model_classification" and (not make or not model):
        raise ValueError(
            f"sample {sample.id} class '{class_label}' is missing reposcan_vehicle_make/reposcan_vehicle_model"
        )
    if task == "vehicle_color_classification" and not color:
        raise ValueError(f"sample {sample.id} class '{class_label}' is missing reposcan_vehicle_color")
    if task == "vehicle_year_classification" and not year:
        raise ValueError(f"sample {sample.id} class '{class_label}' is missing reposcan_vehicle_year")
    return make or None, model or None, year or None, color or None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "image_file",
        "class_label",
        "sample_id",
        "source_filepath",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_color",
        "tags",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_dict_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalized_yolo_line(box: list[float] | tuple[float, float, float, float]) -> str | None:
    if len(box) != 4:
        return None
    x_top_left, y_top_left, width, height = [float(value) for value in box]
    x_top_left = max(0.0, min(1.0, x_top_left))
    y_top_left = max(0.0, min(1.0, y_top_left))
    width = max(0.0, min(1.0 - x_top_left, width))
    height = max(0.0, min(1.0 - y_top_left, height))
    if width <= 0.0 or height <= 0.0:
        return None
    x_center = x_top_left + width / 2.0
    y_center = y_top_left + height / 2.0
    return f"0 {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


def _sample_detections(sample, field_name: str) -> list[Any]:
    detections = _sample_field(sample, field_name)
    if detections is None:
        return []
    return list(getattr(detections, "detections", []) or [])


def _expanded_bbox_pixels(
    bounding_box: list[float] | tuple[float, float, float, float],
    *,
    image_width: int,
    image_height: int,
    padding_ratio: float,
) -> tuple[int, int, int, int] | None:
    if len(bounding_box) != 4:
        return None
    x_top_left, y_top_left, width, height = [float(value) for value in bounding_box]
    if width <= 0.0 or height <= 0.0:
        return None
    pad_x = width * max(padding_ratio, 0.0)
    pad_y = height * max(padding_ratio, 0.0)
    left = max(0, int(round((x_top_left - pad_x) * image_width)))
    top = max(0, int(round((y_top_left - pad_y) * image_height)))
    right = min(image_width, int(round((x_top_left + width + pad_x) * image_width)))
    bottom = min(image_height, int(round((y_top_left + height + pad_y) * image_height)))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _crop_review_fieldnames() -> list[str]:
    return [
        "crop_id",
        "source_sample_id",
        "source_filepath",
        "crop_filepath",
        "source_label",
        "bbox_x",
        "bbox_y",
        "bbox_w",
        "bbox_h",
        "crop_width",
        "crop_height",
        "reposcan_accepted",
        "reposcan_reviewed",
        "reposcan_class_label",
        "reposcan_vehicle_make",
        "reposcan_vehicle_model",
        "reposcan_vehicle_year",
        "reposcan_vehicle_color",
        "reposcan_oklahoma_tags",
        "reviewer_notes",
    ]


def _class_label_for_crop_row(row: dict[str, str], *, task: str) -> str:
    if task == "vehicle_color_classification":
        return _slugify(row.get("reposcan_vehicle_color", ""))
    if task == "vehicle_year_classification":
        return _slugify(row.get("reposcan_vehicle_year", ""))
    return _slugify(row.get("reposcan_class_label", ""))


def _validate_crop_row_fields(row: dict[str, str], *, task: str, class_label: str) -> tuple[str | None, str | None, str | None, str | None]:
    make = str(row.get("reposcan_vehicle_make") or "").strip()
    model = str(row.get("reposcan_vehicle_model") or "").strip()
    year = str(row.get("reposcan_vehicle_year") or "").strip()
    color = str(row.get("reposcan_vehicle_color") or "").strip()
    if not class_label or class_label == "unknown":
        raise ValueError(f"accepted crop {row.get('crop_id', '')} is missing a class label for {task}")
    if task == "vehicle_make_model_classification" and (not make or not model):
        raise ValueError(f"accepted crop {row.get('crop_id', '')} is missing reposcan_vehicle_make/reposcan_vehicle_model")
    if task == "vehicle_color_classification" and not color:
        raise ValueError(f"accepted crop {row.get('crop_id', '')} is missing reposcan_vehicle_color")
    if task == "vehicle_year_classification" and not year:
        raise ValueError(f"accepted crop {row.get('crop_id', '')} is missing reposcan_vehicle_year")
    return make or None, model or None, year or None, color or None


def _split_crop_rows(
    rows: list[dict[str, str]],
    *,
    task: str,
    train_ratio: float,
    validation_ratio: float,
    holdout_ratio: float,
    seed: int,
) -> dict[str, list[dict[str, str]]]:
    ratio_total = train_ratio + validation_ratio + holdout_ratio
    if abs(ratio_total - 1.0) > 1e-6:
        raise ValueError("train, validation, and holdout ratios must add up to 1.0")

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(_class_label_for_crop_row(row, task=task), []).append(row)

    randomizer = random.Random(seed)
    split_map: dict[str, list[dict[str, str]]] = {"train": [], "validation": [], "holdout": []}
    for class_rows in grouped.values():
        shuffled = list(class_rows)
        randomizer.shuffle(shuffled)
        count = len(shuffled)
        if count >= 10:
            validation_count = max(1, int(round(count * validation_ratio)))
            holdout_count = max(1, int(round(count * holdout_ratio)))
        elif count >= 3:
            validation_count = 1
            holdout_count = 1
        elif count == 2:
            validation_count = 1
            holdout_count = 0
        else:
            validation_count = 0
            holdout_count = 0
        if validation_count + holdout_count >= count:
            holdout_count = max(0, count - validation_count - 1)
        train_count = count - validation_count - holdout_count
        split_map["train"].extend(shuffled[:train_count])
        split_map["validation"].extend(shuffled[train_count : train_count + validation_count])
        split_map["holdout"].extend(shuffled[train_count + validation_count :])
    return split_map


def _split_records(records: list[dict[str, Any]], *, train_ratio: float, validation_ratio: float, holdout_ratio: float, seed: int) -> dict[str, list[dict[str, Any]]]:
    ratio_total = train_ratio + validation_ratio + holdout_ratio
    if abs(ratio_total - 1.0) > 1e-6:
        raise ValueError("train, validation, and holdout ratios must add up to 1.0")

    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    count = len(shuffled)
    if count >= 10:
        validation_count = max(1, int(round(count * validation_ratio)))
        holdout_count = max(1, int(round(count * holdout_ratio)))
    elif count >= 3:
        validation_count = 1
        holdout_count = 1
    elif count == 2:
        validation_count = 1
        holdout_count = 0
    else:
        validation_count = 0
        holdout_count = 0
    if validation_count + holdout_count >= count:
        holdout_count = max(0, count - validation_count - 1)
    train_count = count - validation_count - holdout_count
    return {
        "train": shuffled[:train_count],
        "validation": shuffled[train_count : train_count + validation_count],
        "holdout": shuffled[train_count + validation_count :],
    }


def export_detections_yolo(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)
    fo, _ = _require_fiftyone()

    from reposcan_contracts.dataset import (
        AnnotationReview,
        AnnotationTask,
        DatasetAssetRecord,
        DatasetFormat,
        DatasetLicenseTier,
        DatasetProvenance,
        DatasetReviewStatus,
        DatasetSourceKind,
        DatasetSplit,
        DatasetSplitSource,
        DatasetTask,
        LightingCondition,
        TrainingDatasetManifest,
    )

    if DatasetReviewStatus(args.review_status) == DatasetReviewStatus.approved and not args.require_reviewed:
        raise ValueError("--review-status approved requires --require-reviewed for detection exports")

    source_labels = {label.strip() for label in args.source_labels if label.strip()}
    if not source_labels:
        raise ValueError("at least one --source-labels value is required")

    dataset = fo.load_dataset(args.dataset_name)
    records: list[dict[str, Any]] = []
    skipped_without_detections = 0
    skipped_unreviewed = 0
    for sample in dataset:
        if args.require_reviewed:
            if not _truthy(_sample_field(sample, args.accepted_field)) or not _truthy(
                _sample_field(sample, args.reviewed_field)
            ):
                skipped_unreviewed += 1
                continue

        lines: list[str] = []
        labels: list[str] = []
        for detection in _sample_detections(sample, args.detections_field):
            if str(getattr(detection, "label", "") or "") not in source_labels:
                continue
            line = _normalized_yolo_line(getattr(detection, "bounding_box", []))
            if line is None:
                continue
            lines.append(line)
            labels.append(str(detection.label))
        if not lines:
            skipped_without_detections += 1
            continue
        records.append(
            {
                "sample": sample,
                "lines": lines,
                "source_labels": sorted(set(labels)),
            }
        )

    if not records:
        raise ValueError("no samples with matching detections were found")

    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    _prepare_export_root(output_root, overwrite=args.overwrite)
    split_map = _split_records(
        records,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        holdout_ratio=args.holdout_ratio,
        seed=args.seed,
    )

    assets: list[DatasetAssetRecord] = []
    split_sources: list[DatasetSplitSource] = []
    source_rows: list[dict[str, Any]] = []
    for split_name, split_records in split_map.items():
        if not split_records:
            continue
        image_root = output_root / "images" / split_name
        label_root = output_root / "labels" / split_name
        for record in split_records:
            sample = record["sample"]
            source = Path(sample.filepath)
            suffix = source.suffix.lower() or ".jpg"
            filename = f"{sample.id}{suffix}"
            label_filename = f"{sample.id}.txt"
            image_destination = image_root / filename
            label_destination = label_root / label_filename
            _copy_or_link(source, image_destination, copy_mode=args.copy_mode)
            label_destination.parent.mkdir(parents=True, exist_ok=True)
            label_destination.write_text("\n".join(record["lines"]) + "\n", encoding="utf-8")

            tags = list(sample.tags or [])
            for tag in [
                "fiftyone_export",
                "open_images",
                f"detection_class:{args.target_class_name}",
                *[f"open_images_label:{_slugify(label)}" for label in record["source_labels"]],
            ]:
                if tag not in tags:
                    tags.append(tag)
            extra_tags = _split_tag_text(_sample_field(sample, "reposcan_oklahoma_tags", []))
            for tag in extra_tags:
                if tag not in tags:
                    tags.append(tag)

            relative_image = image_destination.relative_to(output_root).as_posix()
            assets.append(
                DatasetAssetRecord(
                    asset_id=f"{split_name}_{sample.id}",
                    relative_path=relative_image,
                    capture_session_id=f"fiftyone_{args.dataset_name}_{split_name}",
                    lighting_conditions=[LightingCondition.unknown],
                    annotations=[AnnotationTask.vehicle_detection],
                    tags=tags,
                )
            )
            source_rows.append(
                {
                    "sample_id": sample.id,
                    "split": split_name,
                    "source_filepath": sample.filepath,
                    "image_file": relative_image,
                    "label_file": label_destination.relative_to(output_root).as_posix(),
                    "source_labels": record["source_labels"],
                    "box_count": len(record["lines"]),
                }
            )

        split_sources.append(
            DatasetSplitSource(
                split=DatasetSplit(split_name),
                relative_path=f"images/{split_name}",
                label_path=f"labels/{split_name}",
                sample_count=len(split_records),
                capture_session_ids=[f"fiftyone_{args.dataset_name}_{split_name}"],
                tags=["fiftyone_export", "open_images", "vehicle_detection"],
            )
        )

    metadata_root = output_root / "metadata"
    metadata_root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(metadata_root / "source_samples.jsonl", source_rows)
    (metadata_root / "export_summary.json").write_text(
        json.dumps(
            {
                "dataset_name": args.dataset_name,
                "detections_field": args.detections_field,
                "source_labels": sorted(source_labels),
                "target_class_name": args.target_class_name,
                "exported_samples": len(records),
                "split_counts": {name: len(items) for name, items in split_map.items()},
                "skipped_without_matching_detections": skipped_without_detections,
                "skipped_unreviewed": skipped_unreviewed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    review_status = DatasetReviewStatus(args.review_status)
    manifest = TrainingDatasetManifest(
        dataset_name=f"{args.dataset_name}-vehicle-detection-yolo",
        dataset_version=args.dataset_version,
        task=DatasetTask.vehicle_detection,
        format=DatasetFormat.yolo_detection,
        storage_root=str(output_root),
        review_status=review_status,
        provenance=DatasetProvenance(
            source_name=f"FiftyOne Open Images detections {args.dataset_name}",
            source_kind=DatasetSourceKind.public_benchmark,
            license_tier=DatasetLicenseTier.unknown if review_status == DatasetReviewStatus.pending else DatasetLicenseTier.public,
            license_name="Open Images per-sample license/provenance review",
            license_reference=f"FiftyOne dataset={args.dataset_name}; metadata/source_samples.jsonl",
            region="us",
            notes="Open Images bounding boxes mapped to one RepoScan vehicle class for detector warm-start training.",
        ),
        annotation_review=(
            AnnotationReview(
                reviewer=args.reviewer,
                reviewed_at_utc=_utcnow(),
                accepted_tasks=[AnnotationTask.vehicle_detection],
                notes="Approved detection labels exported from reviewed FiftyOne source samples.",
            )
            if review_status == DatasetReviewStatus.approved
            else None
        ),
        assets=assets,
        splits=split_sources,
        notes="RepoScan YOLO vehicle-detection dataset exported from FiftyOne detections.",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8")

    print(f"Exported detection samples: {len(records)}")
    print(f"Dataset root: {output_root}")
    print(f"Manifest: {manifest_path}")
    print(json.dumps({"split_counts": {name: len(items) for name, items in split_map.items()}}, indent=2))
    return 0


def export_attribute_crop_review(args: argparse.Namespace) -> int:
    fo, _ = _require_fiftyone()
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to export vehicle attribute crops") from exc

    dataset = fo.load_dataset(args.dataset_name)
    source_labels = {label.strip() for label in args.source_labels if label.strip()}
    if not source_labels:
        raise ValueError("at least one --source-labels value is required")

    output_root = Path(args.output_root).resolve()
    review_csv = Path(args.review_csv).resolve()
    _prepare_export_root(output_root, overwrite=args.overwrite)

    rows: list[dict[str, Any]] = []
    skipped_small = 0
    skipped_invalid = 0
    for sample in dataset:
        source_path = Path(sample.filepath)
        if not source_path.exists():
            skipped_invalid += 1
            continue
        try:
            image = Image.open(source_path).convert("RGB")
        except Exception:
            skipped_invalid += 1
            continue

        with image:
            image_width, image_height = image.size
            for detection_index, detection in enumerate(_sample_detections(sample, args.detections_field)):
                source_label = str(getattr(detection, "label", "") or "")
                if source_label not in source_labels:
                    continue
                bounding_box = list(getattr(detection, "bounding_box", []) or [])
                crop_box = _expanded_bbox_pixels(
                    bounding_box,
                    image_width=image_width,
                    image_height=image_height,
                    padding_ratio=args.padding_ratio,
                )
                if crop_box is None:
                    skipped_invalid += 1
                    continue
                left, top, right, bottom = crop_box
                crop_width = right - left
                crop_height = bottom - top
                if crop_width < args.min_width_px or crop_height < args.min_height_px:
                    skipped_small += 1
                    continue

                crop_id = f"{sample.id}_{detection_index:04d}"
                crop_path = output_root / "crops" / f"{crop_id}.jpg"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                image.crop(crop_box).save(crop_path, format="JPEG", quality=95)
                rows.append(
                    {
                        "crop_id": crop_id,
                        "source_sample_id": sample.id,
                        "source_filepath": str(source_path),
                        "crop_filepath": str(crop_path),
                        "source_label": source_label,
                        "bbox_x": f"{float(bounding_box[0]):.6f}" if len(bounding_box) == 4 else "",
                        "bbox_y": f"{float(bounding_box[1]):.6f}" if len(bounding_box) == 4 else "",
                        "bbox_w": f"{float(bounding_box[2]):.6f}" if len(bounding_box) == 4 else "",
                        "bbox_h": f"{float(bounding_box[3]):.6f}" if len(bounding_box) == 4 else "",
                        "crop_width": crop_width,
                        "crop_height": crop_height,
                        "reposcan_accepted": "false",
                        "reposcan_reviewed": "false",
                        "reposcan_class_label": "",
                        "reposcan_vehicle_make": "",
                        "reposcan_vehicle_model": "",
                        "reposcan_vehicle_year": "",
                        "reposcan_vehicle_color": "",
                        "reposcan_oklahoma_tags": "",
                        "reviewer_notes": "",
                    }
                )
                if args.max_crops is not None and len(rows) >= args.max_crops:
                    break
            if args.max_crops is not None and len(rows) >= args.max_crops:
                break

    _write_dict_csv(review_csv, rows, _crop_review_fieldnames())
    summary = {
        "dataset_name": args.dataset_name,
        "source_labels": sorted(source_labels),
        "exported_crops": len(rows),
        "skipped_small_crops": skipped_small,
        "skipped_invalid_images_or_boxes": skipped_invalid,
        "review_csv": str(review_csv),
    }
    (output_root / "crop_review_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Exported attribute review crops: {len(rows)}")
    print(f"Crop root: {output_root}")
    print(f"Review CSV: {review_csv}")
    print(json.dumps(summary, indent=2))
    return 0


def export_reviewed_crops(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.dataset import (
        AnnotationReview,
        DatasetAssetRecord,
        DatasetFormat,
        DatasetLicenseTier,
        DatasetProvenance,
        DatasetReviewStatus,
        DatasetSourceKind,
        DatasetSplit,
        DatasetSplitSource,
        DatasetTask,
        LightingCondition,
        TrainingDatasetManifest,
    )

    if DatasetReviewStatus(args.review_status) == DatasetReviewStatus.approved and args.allow_unreviewed:
        raise ValueError("--review-status approved cannot be combined with --allow-unreviewed")

    review_csv = Path(args.review_csv).resolve()
    with review_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]

    selected: list[dict[str, str]] = []
    for row in rows:
        if not _truthy(row.get("reposcan_accepted")):
            continue
        if not args.allow_unreviewed and not _truthy(row.get("reposcan_reviewed")):
            continue
        class_label = _class_label_for_crop_row(row, task=args.task)
        _validate_crop_row_fields(row, task=args.task, class_label=class_label)
        selected.append(row)

    if not selected:
        raise ValueError("no accepted reviewed crop rows were found in the review CSV")

    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    _prepare_export_root(output_root, overwrite=args.overwrite)
    split_map = _split_crop_rows(
        selected,
        task=args.task,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        holdout_ratio=args.holdout_ratio,
        seed=args.seed,
    )

    annotation_tasks = _annotation_tasks_for_task(args.task)
    assets: list[DatasetAssetRecord] = []
    split_rows: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "holdout": []}
    class_counts: dict[str, dict[str, int]] = {"train": {}, "validation": {}, "holdout": {}}

    for split_name, split_rows_for_split in split_map.items():
        for row in split_rows_for_split:
            class_label = _class_label_for_crop_row(row, task=args.task)
            make, model, year, color = _validate_crop_row_fields(row, task=args.task, class_label=class_label)
            source = Path(row["crop_filepath"]).resolve()
            if not source.exists():
                raise ValueError(f"reviewed crop image does not exist: {source}")
            suffix = source.suffix.lower() or ".jpg"
            crop_id = _slugify(row.get("crop_id") or source.stem)
            destination = output_root / "splits" / split_name / class_label / f"{crop_id}{suffix}"
            _copy_or_link(source, destination, copy_mode=args.copy_mode)
            relative_path = destination.relative_to(output_root).as_posix()
            tags = ["attribute_crop", "fiftyone_detection_crop"]
            source_label = row.get("source_label", "").strip()
            if source_label:
                tags.append(f"open_images_label:{_slugify(source_label)}")
            for tag in _split_tag_text(row.get("reposcan_oklahoma_tags")):
                if tag not in tags:
                    tags.append(tag)

            split_row = {
                "image_file": relative_path,
                "class_label": class_label,
                "sample_id": row.get("crop_id", ""),
                "source_filepath": row.get("source_filepath", ""),
                "vehicle_make": make or "",
                "vehicle_model": model or "",
                "vehicle_year": year or "",
                "vehicle_color": color or "",
                "tags": "|".join(tags),
            }
            split_rows[split_name].append(split_row)
            class_counts[split_name][class_label] = class_counts[split_name].get(class_label, 0) + 1
            assets.append(
                DatasetAssetRecord(
                    asset_id=f"{split_name}_{crop_id}",
                    relative_path=relative_path,
                    capture_session_id=f"attribute_crops_{args.dataset_name}_{split_name}",
                    lighting_conditions=[LightingCondition.unknown],
                    annotations=annotation_tasks,
                    tags=tags,
                    vehicle_make=make,
                    vehicle_model=model,
                    vehicle_year=year,
                    vehicle_color=color,
                )
            )

    for split_name, rows_for_split in split_rows.items():
        if not rows_for_split:
            continue
        _write_csv(output_root / "splits" / split_name / "labels.csv", rows_for_split)
        _write_jsonl(output_root / "splits" / split_name / "manifest.jsonl", rows_for_split)

    metadata_root = output_root / "metadata"
    metadata_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "class_balance_report.json").write_text(json.dumps(class_counts, indent=2), encoding="utf-8")
    _write_jsonl(metadata_root / "source_crops.jsonl", [row for rows_for_split in split_rows.values() for row in rows_for_split])

    split_sources = []
    for split_name, rows_for_split in split_rows.items():
        if not rows_for_split:
            continue
        split_sources.append(
            DatasetSplitSource(
                split=DatasetSplit(split_name),
                relative_path=f"splits/{split_name}",
                label_path=f"splits/{split_name}/labels.csv",
                sample_count=len(rows_for_split),
                capture_session_ids=[f"attribute_crops_{args.dataset_name}_{split_name}"],
                tags=["attribute_crop", "reviewed_vehicle_attribute"],
            )
        )

    review_status = DatasetReviewStatus(args.review_status)
    manifest = TrainingDatasetManifest(
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        task=DatasetTask(args.task),
        format=DatasetFormat.imagefolder,
        storage_root=str(output_root),
        review_status=review_status,
        provenance=DatasetProvenance(
            source_name=f"Reviewed vehicle attribute crops from {review_csv.name}",
            source_kind=DatasetSourceKind.public_benchmark,
            license_tier=DatasetLicenseTier.unknown if review_status == DatasetReviewStatus.pending else DatasetLicenseTier.public,
            license_name="per-crop upstream dataset license/provenance review",
            license_reference=str(review_csv),
            region="us-ok",
            notes="Vehicle crops exported from public detections and reviewed for attribute classifier training.",
        ),
        annotation_review=(
            AnnotationReview(
                reviewer=args.reviewer,
                reviewed_at_utc=_utcnow(),
                accepted_tasks=annotation_tasks,
                notes="Approved crop-level vehicle attribute labels exported from review CSV.",
            )
            if review_status == DatasetReviewStatus.approved
            else None
        ),
        assets=assets,
        splits=split_sources,
        notes="RepoScan ImageFolder attribute dataset exported from reviewed vehicle crops.",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8")

    print(f"Exported reviewed attribute crops: {sum(len(rows_for_split) for rows_for_split in split_rows.values())}")
    print(f"Dataset root: {output_root}")
    print(f"Manifest: {manifest_path}")
    print(json.dumps({"split_counts": {name: len(rows_for_split) for name, rows_for_split in split_rows.items()}}, indent=2))
    return 0


def export_reviewed(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)
    fo, _ = _require_fiftyone()

    from reposcan_contracts.dataset import (
        AnnotationReview,
        DatasetAssetRecord,
        DatasetFormat,
        DatasetLicenseTier,
        DatasetProvenance,
        DatasetReviewStatus,
        DatasetSourceKind,
        DatasetSplit,
        DatasetSplitSource,
        DatasetTask,
        LightingCondition,
        TrainingDatasetManifest,
    )

    if DatasetReviewStatus(args.review_status) == DatasetReviewStatus.approved and args.allow_unreviewed:
        raise ValueError("--review-status approved cannot be combined with --allow-unreviewed")

    dataset = fo.load_dataset(args.dataset_name)
    selected = []
    for sample in dataset:
        if not _truthy(_sample_field(sample, args.accepted_field)):
            continue
        if not args.allow_unreviewed and not _truthy(_sample_field(sample, args.reviewed_field)):
            continue
        class_label = _slugify(_sample_field(sample, args.class_field, ""))
        if not class_label or class_label == "unknown":
            raise ValueError(f"accepted sample {sample.id} is missing {args.class_field}")
        sample["reposcan_export_class"] = class_label
        selected.append(sample)

    if not selected:
        raise ValueError("no accepted reviewed samples were found in the FiftyOne dataset")

    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    _prepare_export_root(output_root, overwrite=args.overwrite)
    split_map = _split_samples(
        selected,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        holdout_ratio=args.holdout_ratio,
        seed=args.seed,
    )
    annotation_tasks = _annotation_tasks_for_task(args.task)
    assets: list[DatasetAssetRecord] = []
    split_rows: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "holdout": []}
    class_counts: dict[str, dict[str, int]] = {"train": {}, "validation": {}, "holdout": {}}

    for split_name, split_samples in split_map.items():
        for sample in split_samples:
            class_label = _slugify(_sample_field(sample, "reposcan_export_class"))
            make, model, year, color = _validate_label_fields(sample, task=args.task, class_label=class_label)
            source = Path(sample.filepath)
            suffix = source.suffix.lower() or ".jpg"
            filename = f"{sample.id}{suffix}"
            destination = output_root / "splits" / split_name / class_label / filename
            _copy_or_link(source, destination, copy_mode=args.copy_mode)
            relative_path = destination.relative_to(output_root).as_posix()
            tags = list(sample.tags or [])
            extra_tags = _sample_field(sample, "reposcan_oklahoma_tags", []) or []
            if isinstance(extra_tags, str):
                extra_tags = [item.strip() for item in extra_tags.split("|") if item.strip()]
            for tag in extra_tags:
                if tag not in tags:
                    tags.append(tag)

            row = {
                "image_file": relative_path,
                "class_label": class_label,
                "sample_id": sample.id,
                "source_filepath": sample.filepath,
                "vehicle_make": make or "",
                "vehicle_model": model or "",
                "vehicle_year": year or "",
                "vehicle_color": color or "",
                "tags": "|".join(tags),
            }
            split_rows[split_name].append(row)
            class_counts[split_name][class_label] = class_counts[split_name].get(class_label, 0) + 1
            assets.append(
                DatasetAssetRecord(
                    asset_id=f"{split_name}_{sample.id}",
                    relative_path=relative_path,
                    capture_session_id=f"fiftyone_{args.dataset_name}",
                    lighting_conditions=[LightingCondition.unknown],
                    annotations=annotation_tasks,
                    tags=tags,
                    vehicle_make=make,
                    vehicle_model=model,
                    vehicle_year=year,
                    vehicle_color=color,
                )
            )

    for split_name, rows in split_rows.items():
        if not rows:
            continue
        _write_csv(output_root / "splits" / split_name / "labels.csv", rows)
        _write_jsonl(output_root / "splits" / split_name / "manifest.jsonl", rows)

    metadata_root = output_root / "metadata"
    metadata_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "class_balance_report.json").write_text(json.dumps(class_counts, indent=2), encoding="utf-8")
    _write_jsonl(metadata_root / "source_samples.jsonl", [row for rows in split_rows.values() for row in rows])

    split_sources = []
    for split_name, rows in split_rows.items():
        if not rows:
            continue
        split_sources.append(
            DatasetSplitSource(
                split=DatasetSplit(split_name),
                relative_path=f"splits/{split_name}",
                label_path=f"splits/{split_name}/labels.csv",
                sample_count=len(rows),
                tags=["fiftyone_export", "reviewed_vehicle_image"],
            )
        )

    review_status = DatasetReviewStatus(args.review_status)
    manifest = TrainingDatasetManifest(
        dataset_name=args.dataset_name,
        dataset_version=args.dataset_version,
        task=DatasetTask(args.task),
        format=DatasetFormat.imagefolder,
        storage_root=str(output_root),
        review_status=review_status,
        provenance=DatasetProvenance(
            source_name=f"FiftyOne reviewed dataset {args.dataset_name}",
            source_kind=DatasetSourceKind.public_benchmark,
            license_tier=DatasetLicenseTier.unknown if review_status == DatasetReviewStatus.pending else DatasetLicenseTier.public,
            license_name="per-sample upstream dataset license/provenance review",
            license_reference=f"FiftyOne dataset={args.dataset_name}; metadata/source_samples.jsonl",
            region="us-ok",
            notes="Only accepted/reviewed samples were exported. Keep upstream dataset license records with the dataset.",
        ),
        annotation_review=(
            AnnotationReview(
                reviewer=args.reviewer,
                reviewed_at_utc=_utcnow(),
                accepted_tasks=annotation_tasks,
                notes="Approved samples exported from FiftyOne review fields.",
            )
            if review_status == DatasetReviewStatus.approved
            else None
        ),
        assets=assets,
        splits=split_sources,
        notes="RepoScan ImageFolder dataset exported from a reviewed FiftyOne dataset.",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8")

    print(f"Exported samples: {sum(len(rows) for rows in split_rows.values())}")
    print(f"Dataset root: {output_root}")
    print(f"Manifest: {manifest_path}")
    print(json.dumps({"split_counts": {name: len(rows) for name, rows in split_rows.items()}}, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "pull-open-images":
        return pull_open_images(args)
    if args.command == "write-review-template":
        return write_review_template(args)
    if args.command == "apply-review-csv":
        return apply_review_csv(args)
    if args.command == "launch-app":
        return launch_app(args)
    if args.command == "export-attribute-crop-review":
        return export_attribute_crop_review(args)
    if args.command == "export-reviewed-crops":
        return export_reviewed_crops(args)
    if args.command == "export-reviewed":
        return export_reviewed(args)
    if args.command == "export-detections-yolo":
        return export_detections_yolo(args)
    raise ValueError(f"unknown command: {args.command}")


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
