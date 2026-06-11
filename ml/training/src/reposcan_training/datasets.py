from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import yaml

from reposcan_contracts.dataset import (
    AnnotationReview,
    AnnotationTask,
    DatasetAssetRecord,
    DatasetFormat,
    DatasetReviewStatus,
    DatasetSplit,
    DatasetSplitAssignment,
    DatasetSplitManifest,
    DatasetSplitSource,
    TrainingDatasetManifest,
)

from .workflows import resolve_storage_root, utc_now_utc


_STANDARD_SPLIT_ORDER = (
    DatasetSplit.train,
    DatasetSplit.validation,
    DatasetSplit.holdout,
)


@dataclass(frozen=True)
class DetectionDatasetPromotionResult:
    dataset_root: Path
    dataset_manifest_path: Path
    dataset_split_counts: dict[str, int]
    field_eval_root: Path | None = None
    field_eval_manifest_path: Path | None = None
    field_eval_count: int = 0


@dataclass(frozen=True)
class LabelIndexRow:
    asset_id: str
    source_file: str
    image_relative_path: str
    label_relative_path: str
    capture_session_id: str
    planned_split: str
    lighting_conditions: str
    distance_band: str
    expected_plate_text: str
    tags: str
    field_eval_candidate: str


def ensure_detection_capture_manifest(
    manifest: TrainingDatasetManifest,
    *,
    allow_pending: bool,
) -> None:
    if manifest.task.value != "plate_detection":
        raise ValueError("detection curation requires a plate_detection dataset manifest")
    if manifest.format != DatasetFormat.generic_capture:
        raise ValueError("detection curation requires a dataset manifest with format=generic_capture")
    if not manifest.assets:
        raise ValueError("detection curation requires asset-level records in the source manifest")
    if manifest.review_status == DatasetReviewStatus.quarantined:
        raise ValueError(f"dataset manifest '{manifest.dataset_name}' is quarantined")
    if manifest.review_status == DatasetReviewStatus.pending and not allow_pending:
        raise ValueError(
            f"dataset manifest '{manifest.dataset_name}' is still pending review; pass --allow-pending to continue"
        )


def _assignment_map(split_manifest: DatasetSplitManifest) -> dict[str, DatasetSplitAssignment]:
    assignments = {item.asset_id: item for item in split_manifest.assignments}
    if len(assignments) != len(split_manifest.assignments):
        raise ValueError("split manifest assignments must reference each asset_id at most once")
    return assignments


def validate_split_manifest_for_dataset(
    source_manifest: TrainingDatasetManifest,
    split_manifest: DatasetSplitManifest,
) -> dict[str, DatasetSplitAssignment]:
    if split_manifest.dataset_name != source_manifest.dataset_name:
        raise ValueError("split manifest dataset_name does not match the source dataset manifest")
    if split_manifest.dataset_version not in (None, source_manifest.dataset_version):
        raise ValueError("split manifest dataset_version does not match the source dataset manifest")

    assignments = _assignment_map(split_manifest)
    asset_ids = {asset.asset_id for asset in source_manifest.assets}
    missing = sorted(asset_ids - set(assignments))
    extras = sorted(set(assignments) - asset_ids)
    if missing:
        raise ValueError(f"split manifest is missing assignments for asset_ids: {', '.join(missing[:10])}")
    if extras:
        raise ValueError(f"split manifest references unknown asset_ids: {', '.join(extras[:10])}")
    return assignments


def label_relative_path(relative_image_path: str) -> str:
    return str(Path(relative_image_path).with_suffix(".txt")).replace("\\", "/")


def build_detection_label_index_rows(
    *,
    repo_root: Path,
    source_manifest: TrainingDatasetManifest,
    split_manifest: DatasetSplitManifest | None = None,
) -> list[LabelIndexRow]:
    assignments = _assignment_map(split_manifest) if split_manifest is not None else {}
    storage_root = resolve_storage_root(repo_root, source_manifest.storage_root)
    rows: list[LabelIndexRow] = []
    for asset in sorted(source_manifest.assets, key=lambda item: (item.capture_session_id, item.relative_path, item.asset_id)):
        assignment = assignments.get(asset.asset_id)
        rows.append(
            LabelIndexRow(
                asset_id=asset.asset_id,
                source_file=str((storage_root / asset.relative_path).resolve()),
                image_relative_path=asset.relative_path,
                label_relative_path=label_relative_path(asset.relative_path),
                capture_session_id=asset.capture_session_id,
                planned_split=assignment.split.value if assignment is not None else "",
                lighting_conditions="|".join(condition.value for condition in asset.lighting_conditions),
                distance_band=asset.distance_band.value if asset.distance_band is not None else "",
                expected_plate_text=asset.expected_plate_text or "",
                tags="|".join(asset.tags),
                field_eval_candidate="true" if asset.field_eval_candidate else "false",
            )
        )
    return rows


def write_detection_label_index(path: Path, rows: Sequence[LabelIndexRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "asset_id",
                "source_file",
                "image_relative_path",
                "label_relative_path",
                "capture_session_id",
                "planned_split",
                "lighting_conditions",
                "distance_band",
                "expected_plate_text",
                "tags",
                "field_eval_candidate",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def _validate_yolo_line(line: str, *, line_number: int, path: Path) -> None:
    parts = line.split()
    if len(parts) != 5:
        raise ValueError(f"{path}: line {line_number} must contain 5 space-delimited values")
    try:
        class_id = int(parts[0])
        coordinates = [float(value) for value in parts[1:]]
    except ValueError as exc:
        raise ValueError(f"{path}: line {line_number} contains a non-numeric YOLO value") from exc
    if class_id < 0:
        raise ValueError(f"{path}: line {line_number} has a negative class id")
    x_center, y_center, width, height = coordinates
    for value_name, value in (
        ("x_center", x_center),
        ("y_center", y_center),
        ("width", width),
        ("height", height),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{path}: line {line_number} has {value_name} outside the [0, 1] range")
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"{path}: line {line_number} must have positive width and height")


def validate_yolo_label_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"missing YOLO label file: {path}")
    content = path.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in content if line.strip()]
    if not lines:
        raise ValueError(f"YOLO label file is empty: {path}")
    for line_number, line in enumerate(lines, start=1):
        _validate_yolo_line(line, line_number=line_number, path=path)


def _copy_or_link_file(source: Path, destination: Path, *, copy_mode: str) -> None:
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


def _build_annotation_review(
    *,
    reviewer: str,
    reviewed_at_utc: str | None,
    accepted_tasks: Iterable[AnnotationTask],
    notes: str | None,
) -> AnnotationReview:
    return AnnotationReview(
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc or utc_now_utc(),
        accepted_tasks=list(accepted_tasks),
        notes=notes,
    )


def _promoted_asset(
    asset: DatasetAssetRecord,
    *,
    relative_path: Path,
) -> DatasetAssetRecord:
    data = asset.model_dump(mode="json")
    data["relative_path"] = relative_path.as_posix()
    annotations = set(data.get("annotations", []))
    annotations.add(AnnotationTask.plate_detection.value)
    data["annotations"] = sorted(annotations)
    return DatasetAssetRecord.model_validate(data)


def _promoted_image_relative_path(asset: DatasetAssetRecord, *, split: DatasetSplit) -> Path:
    suffix = Path(asset.relative_path).suffix or ".jpg"
    return Path("images") / split.value / f"{asset.asset_id}{suffix.lower()}"


def _promoted_label_relative_path(asset: DatasetAssetRecord, *, split: DatasetSplit) -> Path:
    return Path("labels") / split.value / f"{asset.asset_id}.txt"


def _write_manifest(path: Path, manifest: TrainingDatasetManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )


def promote_detection_dataset(
    *,
    repo_root: Path,
    source_manifest: TrainingDatasetManifest,
    source_manifest_path: Path,
    split_manifest: DatasetSplitManifest,
    labels_root: Path,
    output_root: Path,
    dataset_manifest_path: Path,
    field_eval_manifest_path: Path | None,
    dataset_name: str,
    dataset_version: str,
    reviewer: str,
    reviewed_at_utc: str | None,
    review_notes: str | None,
    allow_pending: bool,
    copy_mode: str,
    accepted_tasks: Sequence[AnnotationTask],
) -> DetectionDatasetPromotionResult:
    ensure_detection_capture_manifest(source_manifest, allow_pending=allow_pending)
    assignments = validate_split_manifest_for_dataset(source_manifest, split_manifest)
    storage_root = resolve_storage_root(repo_root, source_manifest.storage_root)

    dataset_root = output_root / dataset_name
    field_eval_root = output_root / f"{dataset_name}-field-eval"
    annotation_review = _build_annotation_review(
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        accepted_tasks=accepted_tasks or [AnnotationTask.plate_detection],
        notes=review_notes,
    )

    split_counts = {split.value: 0 for split in _STANDARD_SPLIT_ORDER}
    promoted_assets: list[DatasetAssetRecord] = []
    eval_assets: list[DatasetAssetRecord] = []
    field_eval_sessions: set[str] = set()

    for asset in sorted(source_manifest.assets, key=lambda item: (item.capture_session_id, item.relative_path, item.asset_id)):
        assignment = assignments[asset.asset_id]
        source_image = storage_root / asset.relative_path
        if not source_image.exists():
            raise ValueError(f"missing source capture image: {source_image}")
        source_label = labels_root / label_relative_path(asset.relative_path)
        validate_yolo_label_file(source_label)

        if assignment.split == DatasetSplit.field_eval:
            promoted_root = field_eval_root
            relative_image = _promoted_image_relative_path(asset, split=DatasetSplit.field_eval)
            relative_label = _promoted_label_relative_path(asset, split=DatasetSplit.field_eval)
            field_eval_sessions.add(asset.capture_session_id)
        else:
            promoted_root = dataset_root
            relative_image = _promoted_image_relative_path(asset, split=assignment.split)
            relative_label = _promoted_label_relative_path(asset, split=assignment.split)
            split_counts[assignment.split.value] += 1

        _copy_or_link_file(source_image, promoted_root / relative_image, copy_mode=copy_mode)
        _copy_or_link_file(source_label, promoted_root / relative_label, copy_mode=copy_mode)
        promoted = _promoted_asset(asset, relative_path=relative_image)
        if assignment.split == DatasetSplit.field_eval:
            eval_assets.append(promoted)
        else:
            promoted_assets.append(promoted)

    dataset_manifest = TrainingDatasetManifest(
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        task=source_manifest.task,
        format=DatasetFormat.yolo_detection,
        storage_root=str(dataset_root),
        review_status=DatasetReviewStatus.approved,
        provenance=source_manifest.provenance,
        annotation_review=annotation_review,
        assets=promoted_assets,
        splits=[
            DatasetSplitSource(
                split=split,
                relative_path=f"images/{split.value}",
                label_path=f"labels/{split.value}",
                sample_count=split_counts[split.value],
                capture_session_ids=sorted(
                    {
                        asset.capture_session_id
                        for asset in source_manifest.assets
                        if assignments[asset.asset_id].split == split
                    }
                ),
            )
            for split in _STANDARD_SPLIT_ORDER
            if split_counts[split.value] > 0
        ],
        notes=(
            f"Promoted from {source_manifest_path} using {split_manifest.source_manifest_path or 'split manifest'}; "
            "label files validated as YOLO format before promotion."
        ),
    )
    _write_manifest(dataset_manifest_path, dataset_manifest)

    field_eval_manifest: TrainingDatasetManifest | None = None
    if eval_assets:
        field_eval_manifest = TrainingDatasetManifest(
            dataset_name=f"{dataset_name}-field-eval",
            dataset_version=dataset_version,
            task=source_manifest.task,
            format=DatasetFormat.eval_holdout,
            storage_root=str(field_eval_root),
            review_status=DatasetReviewStatus.approved,
            provenance=source_manifest.provenance,
            annotation_review=annotation_review,
            assets=eval_assets,
            splits=[
                DatasetSplitSource(
                    split=DatasetSplit.field_eval,
                    relative_path="images/field_eval",
                    label_path="labels/field_eval",
                    sample_count=len(eval_assets),
                    capture_session_ids=sorted(field_eval_sessions),
                    tags=sorted({tag for asset in source_manifest.assets for tag in asset.tags if assignments[asset.asset_id].split == DatasetSplit.field_eval}),
                )
            ],
            notes=(
                f"Dedicated field-eval holdout promoted from {source_manifest_path}; "
                "keep this dataset separate from train/validation/holdout usage."
            ),
        )
        if field_eval_manifest_path is None:
            raise ValueError("field_eval assignments exist but no --field-eval-manifest output path was provided")
        _write_manifest(field_eval_manifest_path, field_eval_manifest)

    return DetectionDatasetPromotionResult(
        dataset_root=dataset_root,
        dataset_manifest_path=dataset_manifest_path,
        dataset_split_counts={name: count for name, count in split_counts.items() if count > 0},
        field_eval_root=field_eval_root if field_eval_manifest is not None else None,
        field_eval_manifest_path=field_eval_manifest_path if field_eval_manifest is not None else None,
        field_eval_count=len(eval_assets),
    )
