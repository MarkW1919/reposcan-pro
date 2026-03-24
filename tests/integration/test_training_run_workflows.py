from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_profile(example_name: str, output_root: Path, destination: Path) -> Path:
    source = REPO_ROOT / "configs" / "training" / example_name
    profile = yaml.safe_load(source.read_text(encoding="utf-8"))
    profile["output_root"] = output_root.as_posix()
    destination.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    return destination


def test_detection_training_script_prepares_workspace(tmp_path):
    storage_root = tmp_path / "plate_dataset"
    for split in ("train", "validation", "holdout"):
        (storage_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (storage_root / "labels" / split).mkdir(parents=True, exist_ok=True)
        (storage_root / "images" / split / f"{split}_0001.jpg").write_bytes(b"img")
        (storage_root / "labels" / split / f"{split}_0001.txt").write_text("0 0.5 0.5 0.2 0.1\n", encoding="utf-8")

    manifest_path = tmp_path / "plate-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-plate-yolo",
                "dataset_version: 1",
                "task: plate_detection",
                "format: yolo_detection",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-plate-dataset",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-plate",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:00:00Z",
                "  accepted_tasks: [plate_detection]",
                "splits:",
                "  - split: train",
                "    relative_path: images/train",
                "    label_path: labels/train",
                "  - split: validation",
                "    relative_path: images/validation",
                "    label_path: labels/validation",
                "  - split: holdout",
                "    relative_path: images/holdout",
                "    label_path: labels/holdout",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-detector-finetune.yaml", tmp_path / "runs", tmp_path / "plate-profile.yaml")
    result = _run_script(
        "scripts/train_detection_model.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "plate-detection-smoke",
        "--dry-run",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dataset.yaml" in result.stdout
    assert "yolo" in result.stdout


def test_attribute_training_script_prepares_workspace(tmp_path):
    storage_root = tmp_path / "vehicle_color_dataset"
    for split in ("train", "validation"):
        for class_name in ("white", "black"):
            class_dir = storage_root / split / class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            (class_dir / f"{class_name}_0001.jpg").write_bytes(b"img")

    manifest_path = tmp_path / "vehicle-color.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-vehicle-color",
                "dataset_version: 1",
                "task: vehicle_color_classification",
                "format: imagefolder",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-color-dataset",
                "  source_kind: internal_generated",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-color",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:05:00Z",
                "  accepted_tasks: [vehicle_color]",
                "splits:",
                "  - split: train",
                "    relative_path: train",
                "  - split: validation",
                "    relative_path: validation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("vehicle-color-classifier.yaml", tmp_path / "runs", tmp_path / "color-profile.yaml")
    result = _run_script(
        "scripts/train_attribute_classifier.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "vehicle-color-smoke",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "class_index.json" in result.stdout
    assert "Preparation complete. Training was not started." in result.stdout


def test_ocr_training_script_prepares_workspace(tmp_path):
    storage_root = tmp_path / "ocr_dataset"
    for split in ("train", "validation", "holdout"):
        image_root = storage_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (storage_root / split / "labels.csv").write_text(
            "image_file,plate_text\nimages/{split}_0001.png,ABC123\n".replace("{split}", split),
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "ocr-smoke",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "us_plate_dict.txt" in result.stdout
    assert "Preparation complete. Training was not started." in result.stdout


def test_ocr_training_script_mixes_synthetic_support_dataset(tmp_path):
    primary_root = tmp_path / "primary_ocr_dataset"
    support_root = tmp_path / "support_ocr_dataset"

    for index in range(10):
        image_root = primary_root / "train" / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"train_{index:04d}.png").write_bytes(b"img")
    for split in ("validation", "holdout"):
        image_root = primary_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        for index in range(2):
            (image_root / f"{split}_{index:04d}.png").write_bytes(b"img")

    (primary_root / "train" / "labels.csv").write_text(
        "image_file,plate_text\n" + "\n".join(f"train_{index:04d}.png,ABC12{index}" for index in range(10)) + "\n",
        encoding="utf-8",
    )
    (primary_root / "validation" / "labels.csv").write_text(
        "image_file,plate_text\nvalidation_0000.png,VAL001\nvalidation_0001.png,VAL002\n",
        encoding="utf-8",
    )
    (primary_root / "holdout" / "labels.csv").write_text(
        "image_file,plate_text\nholdout_0000.png,HLD001\nholdout_0001.png,HLD002\n",
        encoding="utf-8",
    )

    for index in range(8):
        image_root = support_root / "train" / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"support_{index:04d}.png").write_bytes(b"img")
    for split in ("validation", "holdout"):
        image_root = support_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_support_0000.png").write_bytes(b"img")

    (support_root / "train" / "labels.csv").write_text(
        "image_file,plate_text\n" + "\n".join(f"support_{index:04d}.png,SUP12{index}" for index in range(8)) + "\n",
        encoding="utf-8",
    )
    (support_root / "validation" / "labels.csv").write_text(
        "image_file,plate_text\nvalidation_support_0000.png,SUPVAL1\n",
        encoding="utf-8",
    )
    (support_root / "holdout" / "labels.csv").write_text(
        "image_file,plate_text\nholdout_support_0000.png,SUPHLD1\n",
        encoding="utf-8",
    )

    primary_manifest = tmp_path / "primary-ocr.yaml"
    primary_manifest.write_text(
        "\n".join(
            [
                "dataset_name: tmp-primary-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {primary_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-primary-ocr-dataset",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-primary-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-24T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    support_manifest = tmp_path / "support-ocr.yaml"
    support_manifest.write_text(
        "\n".join(
            [
                "dataset_name: tmp-support-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {support_root.as_posix()}",
                "review_status: pending",
                "provenance:",
                "  source_name: tmp-support-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-support-ocr",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(primary_manifest),
        "--support-dataset-manifest",
        str(support_manifest),
        "--run-name",
        "ocr-support-smoke",
        "--allow-pending",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    workspace_dir = tmp_path / "runs" / "ocr-support-smoke"
    train_list = (workspace_dir / "train_list.txt").read_text(encoding="utf-8").strip().splitlines()
    validation_list = (workspace_dir / "validation_list.txt").read_text(encoding="utf-8").strip().splitlines()
    support_summary = json.loads((workspace_dir / "ocr_support_mix_summary.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((workspace_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert len(train_list) == 12
    assert len(validation_list) == 2
    assert support_summary["selected_support_train_rows"] == 2
    assert support_summary["max_support_train_rows"] == 2
    assert support_summary["support_datasets"][0]["selected_train_rows"] == 2
    assert run_manifest["auxiliary_dataset_manifest_paths"] == [str(support_manifest)]


def test_ocr_support_manifest_requires_positive_ratio(tmp_path):
    dataset_root = tmp_path / "ocr_dataset"
    support_root = tmp_path / "support_ocr_dataset"

    for split in ("train", "validation"):
        image_root = dataset_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (dataset_root / split / "labels.csv").write_text(
            f"image_file,plate_text\n{split}_0001.png,ABC123\n",
            encoding="utf-8",
        )
    (dataset_root / "holdout" / "images").mkdir(parents=True, exist_ok=True)
    (dataset_root / "holdout" / "images" / "holdout_0001.png").write_bytes(b"img")
    (dataset_root / "holdout" / "labels.csv").write_text("image_file,plate_text\nholdout_0001.png,ABC123\n", encoding="utf-8")

    (support_root / "train" / "images").mkdir(parents=True, exist_ok=True)
    (support_root / "train" / "images" / "support_0001.png").write_bytes(b"img")
    (support_root / "train" / "labels.csv").write_text("image_file,plate_text\nsupport_0001.png,SUP123\n", encoding="utf-8")
    for split in ("validation", "holdout"):
        (support_root / split / "images").mkdir(parents=True, exist_ok=True)
        (support_root / split / "images" / f"{split}_support_0001.png").write_bytes(b"img")
        (support_root / split / "labels.csv").write_text(
            f"image_file,plate_text\n{split}_support_0001.png,SUP123\n",
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {dataset_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-24T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    support_manifest = tmp_path / "support-ocr.yaml"
    support_manifest.write_text(
        "\n".join(
            [
                "dataset_name: tmp-support-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {support_root.as_posix()}",
                "review_status: pending",
                "provenance:",
                "  source_name: tmp-support-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-support-ocr",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile_data["augmentation"]["synthetic_support_ratio"] = 0.0
    profile_path.write_text(yaml.safe_dump(profile_data, sort_keys=False), encoding="utf-8")

    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--support-dataset-manifest",
        str(support_manifest),
        "--run-name",
        "ocr-support-zero-ratio",
        "--allow-pending",
    )

    assert result.returncode == 1
    assert "synthetic_support_ratio is 0.0" in result.stderr
