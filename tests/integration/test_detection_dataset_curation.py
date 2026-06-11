from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from PIL import Image

from reposcan_contracts.config.loader import load_training_dataset_manifest
from reposcan_contracts.dataset import DatasetFormat, DatasetSplit


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_image(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=color).save(path)


def _write_yolo_label(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("0 0.51 0.62 0.18 0.09\n", encoding="utf-8")


def test_export_detection_label_index_uses_split_manifest(tmp_path):
    storage_root = tmp_path / "captures"
    _write_image(storage_root / "session_night" / "frame_0001.jpg", color=(20, 20, 20))
    _write_image(storage_root / "session_day" / "frame_0100.jpg", color=(180, 180, 180))

    manifest_path = tmp_path / "capture.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-detection-capture",
                "dataset_version: 1",
                "task: plate_detection",
                "format: generic_capture",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp field capture",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T09:00:00Z",
                "  accepted_tasks: [plate_detection]",
                "assets:",
                "  - asset_id: a1",
                "    relative_path: session_night/frame_0001.jpg",
                "    capture_session_id: session_night",
                "    lighting_conditions: [night]",
                "    distance_band: long_range",
                "    annotations: [plate_detection]",
                "    tags: [low_light, long_range]",
                "    field_eval_candidate: true",
                "  - asset_id: a2",
                "    relative_path: session_day/frame_0100.jpg",
                "    capture_session_id: session_day",
                "    lighting_conditions: [daylight]",
                "    distance_band: medium",
                "    annotations: [plate_detection]",
                "    tags: [daytime]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    split_manifest = tmp_path / "split.yaml"
    split_manifest.write_text(
        "\n".join(
            [
                "split_name: tmp-plan",
                "dataset_name: tmp-detection-capture",
                "dataset_version: 1",
                f"source_manifest_path: {manifest_path.as_posix()}",
                "train_ratio: 0.7",
                "validation_ratio: 0.2",
                "holdout_ratio: 0.1",
                "assignments:",
                "  - asset_id: a1",
                "    capture_session_id: session_night",
                "    split: field_eval",
                "    relative_path: session_night/frame_0001.jpg",
                "    tags: [low_light, long_range]",
                "  - asset_id: a2",
                "    capture_session_id: session_day",
                "    split: train",
                "    relative_path: session_day/frame_0100.jpg",
                "    tags: [daytime]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_csv = tmp_path / "label-index.csv"
    result = _run_script(
        "scripts/export_detection_label_index.py",
        "--dataset-manifest",
        str(manifest_path),
        "--split-manifest",
        str(split_manifest),
        "--output",
        str(output_csv),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with output_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert rows[0]["label_relative_path"] == "session_day/frame_0100.txt"
    assert rows[0]["planned_split"] == "train"
    assert rows[1]["planned_split"] == "field_eval"


def test_promote_detection_dataset_builds_curated_and_eval_manifests(tmp_path):
    storage_root = tmp_path / "captures"
    labels_root = tmp_path / "labels"
    for relative_path, color in (
        ("session_train/frame_0001.jpg", (80, 80, 80)),
        ("session_valid/frame_0002.jpg", (120, 120, 120)),
        ("session_holdout/frame_0003.jpg", (160, 160, 160)),
        ("session_eval/frame_0004.jpg", (20, 20, 20)),
    ):
        image_path = storage_root / relative_path
        _write_image(image_path, color=color)
        _write_yolo_label(labels_root / Path(relative_path).with_suffix(".txt"))

    manifest_path = tmp_path / "capture.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-detection-capture",
                "dataset_version: 2",
                "task: plate_detection",
                "format: generic_capture",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp field capture",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T09:10:00Z",
                "  accepted_tasks: [plate_detection]",
                "assets:",
                "  - asset_id: a1",
                "    relative_path: session_train/frame_0001.jpg",
                "    capture_session_id: session_train",
                "    lighting_conditions: [daylight]",
                "    annotations: [plate_detection]",
                "    tags: [daytime]",
                "  - asset_id: a2",
                "    relative_path: session_valid/frame_0002.jpg",
                "    capture_session_id: session_valid",
                "    lighting_conditions: [dusk]",
                "    annotations: [plate_detection]",
                "    tags: [dusk]",
                "  - asset_id: a3",
                "    relative_path: session_holdout/frame_0003.jpg",
                "    capture_session_id: session_holdout",
                "    lighting_conditions: [daylight]",
                "    annotations: [plate_detection]",
                "    tags: [holdout_candidate]",
                "  - asset_id: a4",
                "    relative_path: session_eval/frame_0004.jpg",
                "    capture_session_id: session_eval",
                "    lighting_conditions: [night]",
                "    distance_band: long_range",
                "    annotations: [plate_detection]",
                "    tags: [low_light, long_range]",
                "    field_eval_candidate: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    split_manifest = tmp_path / "split.yaml"
    split_manifest.write_text(
        "\n".join(
            [
                "split_name: tmp-plan",
                "dataset_name: tmp-detection-capture",
                "dataset_version: 2",
                f"source_manifest_path: {manifest_path.as_posix()}",
                "train_ratio: 0.7",
                "validation_ratio: 0.2",
                "holdout_ratio: 0.1",
                "assignments:",
                "  - asset_id: a1",
                "    capture_session_id: session_train",
                "    split: train",
                "    relative_path: session_train/frame_0001.jpg",
                "  - asset_id: a2",
                "    capture_session_id: session_valid",
                "    split: validation",
                "    relative_path: session_valid/frame_0002.jpg",
                "  - asset_id: a3",
                "    capture_session_id: session_holdout",
                "    split: holdout",
                "    relative_path: session_holdout/frame_0003.jpg",
                "  - asset_id: a4",
                "    capture_session_id: session_eval",
                "    split: field_eval",
                "    relative_path: session_eval/frame_0004.jpg",
                "    tags: [low_light, long_range]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "curated"
    curated_manifest_path = tmp_path / "curated-detection.yaml"
    eval_manifest_path = tmp_path / "field-eval.yaml"

    promote = _run_script(
        "scripts/promote_detection_dataset.py",
        "--dataset-manifest",
        str(manifest_path),
        "--split-manifest",
        str(split_manifest),
        "--labels-root",
        str(labels_root),
        "--output-root",
        str(output_root),
        "--output-manifest",
        str(curated_manifest_path),
        "--field-eval-manifest",
        str(eval_manifest_path),
        "--reviewer",
        "qa_promoter_01",
    )
    assert promote.returncode == 0, promote.stdout + promote.stderr

    curated = load_training_dataset_manifest(curated_manifest_path)
    assert curated.format == DatasetFormat.yolo_detection
    assert curated.review_status.value == "approved"
    assert {split.split for split in curated.splits} == {
        DatasetSplit.train,
        DatasetSplit.validation,
        DatasetSplit.holdout,
    }

    field_eval = load_training_dataset_manifest(eval_manifest_path)
    assert field_eval.format == DatasetFormat.eval_holdout
    assert field_eval.splits[0].split == DatasetSplit.field_eval
    assert len(field_eval.assets) == 1

    assert (output_root / "tmp-detection-capture-yolo-curated" / "images" / "train" / "a1.jpg").exists()
    assert (output_root / "tmp-detection-capture-yolo-curated" / "labels" / "validation" / "a2.txt").exists()
    assert (
        output_root
        / "tmp-detection-capture-yolo-curated-field-eval"
        / "labels"
        / "field_eval"
        / "a4.txt"
    ).exists()

    train = _run_script(
        "scripts/train_detection_model.py",
        "--profile",
        str(REPO_ROOT / "configs" / "training" / "plate-detector-finetune.yaml"),
        "--dataset-manifest",
        str(curated_manifest_path),
        "--run-name",
        "tmp_detection_curated_smoke",
        "--dry-run",
    )
    assert train.returncode == 0, train.stdout + train.stderr
    assert "dataset.yaml" in train.stdout
