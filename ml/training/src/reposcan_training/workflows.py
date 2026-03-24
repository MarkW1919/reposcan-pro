from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import yaml

from reposcan_contracts.dataset import DatasetFormat, DatasetReviewStatus, DatasetSplit, TrainingDatasetManifest
from reposcan_contracts.training import DatasetAdapter, TrainingProfileConfig, TrainingRunManifest


US_PLATE_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def utc_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_run_name(profile_name: str, explicit_run_name: str | None = None) -> str:
    if explicit_run_name:
        return explicit_run_name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{profile_name}_{stamp}"


def resolve_storage_root(repo_root: Path, storage_root: str) -> Path:
    root = Path(storage_root)
    if root.is_absolute():
        return root
    return (repo_root / root).resolve()


def ensure_dataset_review_status(manifest: TrainingDatasetManifest, allow_pending: bool) -> None:
    if manifest.review_status == DatasetReviewStatus.quarantined:
        raise ValueError(f"dataset manifest '{manifest.dataset_name}' is quarantined")
    if manifest.review_status == DatasetReviewStatus.pending and not allow_pending:
        raise ValueError(
            f"dataset manifest '{manifest.dataset_name}' is still pending review; enable allow_pending_review to proceed"
        )


def _split_map(manifest: TrainingDatasetManifest):
    return {split.split: split for split in manifest.splits}


def _require_split(manifest: TrainingDatasetManifest, split: DatasetSplit):
    mapping = _split_map(manifest)
    if split not in mapping:
        raise ValueError(f"dataset manifest '{manifest.dataset_name}' is missing split '{split.value}'")
    return mapping[split]


def prepare_detection_workspace(
    repo_root: Path,
    profile: TrainingProfileConfig,
    manifest: TrainingDatasetManifest,
    workspace_dir: Path,
) -> tuple[list[str], list[str], dict[str, str]]:
    if manifest.format != DatasetFormat.yolo_detection:
        raise ValueError("detection training requires a dataset manifest with format=yolo_detection")

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    train_split = _require_split(manifest, DatasetSplit.train)
    validation_split = _require_split(manifest, DatasetSplit.validation)
    holdout_split = _split_map(manifest).get(DatasetSplit.holdout)

    for split_config in (train_split, validation_split, holdout_split):
        if split_config is None:
            continue
        image_root = storage_root / split_config.relative_path
        if not image_root.exists():
            raise ValueError(f"detection split path does not exist: {image_root}")
        if split_config.label_path is not None:
            label_root = storage_root / split_config.label_path
            if not label_root.exists():
                raise ValueError(f"detection label path does not exist: {label_root}")

    dataset_yaml = workspace_dir / "dataset.yaml"
    dataset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(storage_root),
                "train": train_split.relative_path,
                "val": validation_split.relative_path,
                "test": holdout_split.relative_path if holdout_split is not None else None,
                "names": list(profile.class_names),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    prepared_files = [str(dataset_yaml)]
    notes = [
        f"class_names={','.join(profile.class_names)}",
        f"dataset_root={storage_root}",
    ]
    context = {
        "dataset_yaml": str(dataset_yaml),
        "storage_root": str(storage_root),
    }
    return prepared_files, notes, context


def _scan_imagefolder_classes(path: Path) -> dict[str, int]:
    classes: dict[str, int] = {}
    for class_dir in sorted(path.iterdir()):
        if not class_dir.is_dir():
            continue
        count = sum(1 for item in class_dir.rglob("*") if item.is_file())
        if count > 0:
            classes[class_dir.name] = count
    return classes


def prepare_classification_workspace(
    repo_root: Path,
    profile: TrainingProfileConfig,
    manifest: TrainingDatasetManifest,
    workspace_dir: Path,
) -> tuple[list[str], list[str], dict[str, str]]:
    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    mapping = _split_map(manifest)
    train_split = _require_split(manifest, DatasetSplit.train)
    holdout_split = mapping.get(DatasetSplit.holdout)
    validation_split = mapping.get(DatasetSplit.validation)

    train_root = storage_root / train_split.relative_path
    if not train_root.exists():
        raise ValueError(f"training split path does not exist: {train_root}")

    prepared_files: list[str] = []
    notes = [f"dataset_root={storage_root}"]
    context = {
        "storage_root": str(storage_root),
        "train_root": str(train_root),
        "validation_root": str(storage_root / validation_split.relative_path) if validation_split else "",
        "holdout_root": str(storage_root / holdout_split.relative_path) if holdout_split else "",
    }

    if profile.dataset_adapter == DatasetAdapter.stanford_cars:
        summary_path = workspace_dir / "stanford_dataset_summary.json"
        summary = {
            "adapter": profile.dataset_adapter.value,
            "storage_root": str(storage_root),
            "splits": {
                split.split.value: {
                    "path": str(storage_root / split.relative_path),
                    "sample_count": split.sample_count,
                }
                for split in manifest.splits
            },
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        prepared_files.append(str(summary_path))
        notes.append("execution requires scipy to parse Stanford Cars metadata")
    else:
        class_counts = _scan_imagefolder_classes(train_root)
        if len(class_counts) < 2:
            raise ValueError(f"classification training requires at least 2 populated classes under {train_root}")
        class_index_path = workspace_dir / "class_index.json"
        class_index_path.write_text(
            json.dumps(
                {
                    "adapter": profile.dataset_adapter.value,
                    "train_root": str(train_root),
                    "classes": list(class_counts.keys()),
                    "counts": class_counts,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        prepared_files.append(str(class_index_path))
        notes.append(f"class_count={len(class_counts)}")

    return prepared_files, notes, context


def _resolve_csv_image(storage_root: Path, image_root: Path, raw_value: str) -> Path:
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate

    candidates = [
        image_root / candidate,
        image_root / candidate.name,
        storage_root / candidate,
    ]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return (image_root / candidate.name).resolve()


def _read_ocr_labels(storage_root: Path, image_root: Path, labels_path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with labels_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            image_value = str(row.get("image_file") or row.get("filename") or "").strip()
            text_value = str(row.get("plate_text") or row.get("text") or "").strip().upper()
            if not image_value or not text_value:
                continue
            image_path = _resolve_csv_image(storage_root, image_root, image_value)
            relative_path = image_path.relative_to(storage_root).as_posix()
            rows.append((relative_path, text_value))
    return rows


def _read_ocr_split_rows(storage_root: Path, split_config) -> list[tuple[str, str]]:
    if split_config.label_path is None:
        raise ValueError(f"OCR split '{split_config.split.value}' requires label_path")
    image_root = storage_root / split_config.relative_path
    labels_path = storage_root / split_config.label_path
    if not image_root.exists():
        raise ValueError(f"OCR split path does not exist: {image_root}")
    if not labels_path.exists():
        raise ValueError(f"OCR label path does not exist: {labels_path}")
    return _read_ocr_labels(storage_root, image_root, labels_path)


def _write_ocr_list(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = [f"{relative_path}\t{text}" for relative_path, text in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _sample_support_rows(rows: list, *, limit: int, seed: int) -> list:
    if limit <= 0 or not rows:
        return []
    if len(rows) <= limit:
        return list(rows)
    generator = random.Random(seed)
    indexed_rows = list(enumerate(rows))
    generator.shuffle(indexed_rows)
    selected = sorted(indexed_rows[:limit], key=lambda item: item[0])
    return [row for _, row in selected]


def prepare_ocr_workspace(
    repo_root: Path,
    profile: TrainingProfileConfig,
    manifest: TrainingDatasetManifest,
    workspace_dir: Path,
    *,
    support_manifests: list[TrainingDatasetManifest] | None = None,
    support_manifest_paths: list[Path] | None = None,
) -> tuple[list[str], list[str], dict[str, str]]:
    if manifest.format != DatasetFormat.ocr_manifest:
        raise ValueError("OCR training requires a dataset manifest with format=ocr_manifest")

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    mapping = _split_map(manifest)
    train_split = _require_split(manifest, DatasetSplit.train)
    validation_split = _require_split(manifest, DatasetSplit.validation)
    holdout_split = mapping.get(DatasetSplit.holdout)

    train_rows = _read_ocr_split_rows(storage_root, train_split)
    validation_rows = _read_ocr_split_rows(storage_root, validation_split)
    train_list = workspace_dir / "train_list.txt"
    validation_list = workspace_dir / "validation_list.txt"

    support_manifests = support_manifests or []
    support_manifest_paths = support_manifest_paths or []
    support_summary = {
        "primary_dataset_name": manifest.dataset_name,
        "primary_dataset_version": manifest.dataset_version,
        "primary_train_rows": len(train_rows),
        "synthetic_support_ratio": profile.augmentation.synthetic_support_ratio,
        "support_datasets": [],
        "selected_support_train_rows": 0,
    }

    if support_manifests:
        if profile.augmentation.synthetic_support_ratio <= 0.0:
            raise ValueError(
                "OCR support dataset manifests were provided, but profile augmentation.synthetic_support_ratio is 0.0"
            )

        synthetic_rows: list[tuple[int, tuple[str, str]]] = []
        max_support_rows = int(len(train_rows) * profile.augmentation.synthetic_support_ratio)
        support_summary["max_support_train_rows"] = max_support_rows

        for index, support_manifest in enumerate(support_manifests):
            if support_manifest.task != manifest.task:
                raise ValueError("OCR support dataset task must match the primary OCR dataset task")
            if support_manifest.format != DatasetFormat.ocr_manifest:
                raise ValueError("OCR support dataset manifests must use format=ocr_manifest")
            if support_manifest.provenance.source_kind.value != "synthetic":
                raise ValueError("OCR support dataset manifests must come from synthetic provenance")

            support_storage_root = resolve_storage_root(repo_root, support_manifest.storage_root)
            support_train_split = _require_split(support_manifest, DatasetSplit.train)
            support_train_rows = _read_ocr_split_rows(support_storage_root, support_train_split)
            synthetic_rows.extend((index, row) for row in support_train_rows)
            support_summary["support_datasets"].append(
                {
                    "dataset_name": support_manifest.dataset_name,
                    "dataset_version": support_manifest.dataset_version,
                    "dataset_manifest_path": (
                        str(support_manifest_paths[index]) if index < len(support_manifest_paths) else ""
                    ),
                    "available_train_rows": len(support_train_rows),
                }
            )

        selected_support_rows = _sample_support_rows(
            synthetic_rows,
            limit=max_support_rows,
            seed=profile.seed,
        )
        train_rows = [*train_rows, *(row for _, row in selected_support_rows)]
        support_summary["selected_support_train_rows"] = len(selected_support_rows)
        selected_by_dataset: dict[int, int] = {}
        for dataset_index, _ in selected_support_rows:
            selected_by_dataset[dataset_index] = selected_by_dataset.get(dataset_index, 0) + 1
        for dataset_index, item in enumerate(support_summary["support_datasets"]):
            item["selected_train_rows"] = selected_by_dataset.get(dataset_index, 0)
    else:
        support_summary["max_support_train_rows"] = 0

    _write_ocr_list(train_list, train_rows)
    _write_ocr_list(validation_list, validation_rows)
    prepared_files = [str(train_list), str(validation_list)]
    context = {
        "storage_root": str(storage_root),
        "train_list": str(train_list),
        "validation_list": str(validation_list),
    }

    if holdout_split is not None:
        holdout_rows = _read_ocr_split_rows(storage_root, holdout_split)
        holdout_list = workspace_dir / "holdout_list.txt"
        _write_ocr_list(holdout_list, holdout_rows)
        prepared_files.append(str(holdout_list))
        context["holdout_list"] = str(holdout_list)

    char_dict_path = workspace_dir / "us_plate_dict.txt"
    char_dict_path.write_text("\n".join(US_PLATE_CHARS) + "\n", encoding="utf-8")
    prepared_files.append(str(char_dict_path))
    context["char_dict_path"] = str(char_dict_path)

    if support_manifests:
        support_summary_path = workspace_dir / "ocr_support_mix_summary.json"
        support_summary_path.write_text(json.dumps(support_summary, indent=2), encoding="utf-8")
        prepared_files.append(str(support_summary_path))
        context["support_mix_summary"] = str(support_summary_path)

    notes = [
        f"dataset_root={storage_root}",
        "char_dict=US alphanumeric uppercase",
    ]
    if support_manifests:
        notes.append(f"synthetic_support_train_rows={support_summary['selected_support_train_rows']}")
        notes.append(f"synthetic_support_ratio={profile.augmentation.synthetic_support_ratio}")
    return prepared_files, notes, context


def build_run_manifest(
    *,
    profile: TrainingProfileConfig,
    manifest: TrainingDatasetManifest,
    dataset_manifest_path: Path,
    workspace_dir: Path,
    run_name: str,
    prepared_files: list[str],
    training_command: list[str],
    export_command: list[str] | None = None,
    notes: list[str] | None = None,
    auxiliary_dataset_manifest_paths: list[str] | None = None,
) -> TrainingRunManifest:
    return TrainingRunManifest(
        run_name=run_name,
        profile_name=profile.profile_name,
        task=profile.task,
        framework=profile.framework,
        dataset_name=manifest.dataset_name,
        dataset_version=manifest.dataset_version,
        dataset_manifest_path=str(dataset_manifest_path),
        auxiliary_dataset_manifest_paths=auxiliary_dataset_manifest_paths or [],
        prepared_at_utc=utc_now_utc(),
        workspace_dir=str(workspace_dir),
        prepared_files=prepared_files,
        training_command=training_command,
        export_command=export_command or [],
        notes=notes or [],
    )
