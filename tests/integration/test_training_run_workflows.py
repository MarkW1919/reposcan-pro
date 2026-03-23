from __future__ import annotations

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
