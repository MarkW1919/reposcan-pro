from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from reposcan_contracts.config.loader import load_dataset_split_manifest, load_training_dataset_manifest
from reposcan_contracts.dataset import DatasetSplit


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_dataset_workspace_creates_expected_layout(tmp_path):
    workspace_root = tmp_path / "data"
    result = _run_script("scripts/init_dataset_workspace.py", "--root", str(workspace_root))

    assert result.returncode == 0, result.stderr
    for name in ("raw", "staged", "curated", "eval", "manifests"):
        assert (workspace_root / name).is_dir()
    assert (workspace_root / "README.md").exists()


def test_validate_and_plan_capture_manifest(tmp_path):
    storage_root = tmp_path / "dataset"
    (storage_root / "session_night").mkdir(parents=True)
    (storage_root / "session_day").mkdir(parents=True)
    for relative_path in (
        Path("session_night/frame_0001.jpg"),
        Path("session_night/frame_0002.jpg"),
        Path("session_day/frame_0100.jpg"),
    ):
        target = storage_root / relative_path
        target.write_bytes(b"fake-image")

    manifest_path = tmp_path / "capture.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-capture",
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
                "  reviewed_at_utc: 2026-03-23T06:00:00Z",
                "  accepted_tasks: [plate_detection, plate_ocr]",
                "assets:",
                "  - asset_id: a1",
                "    relative_path: session_night/frame_0001.jpg",
                "    capture_session_id: session_night",
                "    lighting_conditions: [night]",
                "    annotations: [plate_detection, plate_ocr]",
                "    expected_plate_text: 8ABC123",
                "    tags: [low_light, long_range]",
                "    field_eval_candidate: true",
                "  - asset_id: a2",
                "    relative_path: session_night/frame_0002.jpg",
                "    capture_session_id: session_night",
                "    lighting_conditions: [night]",
                "    annotations: [plate_detection, plate_ocr]",
                "    expected_plate_text: 8ABC123",
                "    tags: [low_light]",
                "  - asset_id: a3",
                "    relative_path: session_day/frame_0100.jpg",
                "    capture_session_id: session_day",
                "    lighting_conditions: [daylight]",
                "    annotations: [plate_detection, plate_ocr]",
                "    expected_plate_text: 7XYZ001",
                "    tags: [daytime]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    validate = _run_script(
        "scripts/validate_training_dataset_manifest.py",
        "--manifest",
        str(manifest_path),
        "--verify-files",
        "--require-approved",
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr

    split_path = tmp_path / "split.yaml"
    split = _run_script(
        "scripts/plan_training_dataset_split.py",
        "--manifest",
        str(manifest_path),
        "--output",
        str(split_path),
        "--field-eval-tag",
        "long_range",
        "--field-eval-tag",
        "low_light",
    )
    assert split.returncode == 0, split.stdout + split.stderr

    split_manifest = load_dataset_split_manifest(split_path)
    assert any(item.split == DatasetSplit.field_eval for item in split_manifest.assignments)
    day_session_splits = {
        item.split for item in split_manifest.assignments if item.capture_session_id == "session_day"
    }
    assert len(day_session_splits) == 1


def test_import_legacy_training_sources_builds_manifests_from_external_root(tmp_path):
    legacy_root = tmp_path / "legacy"
    cars_train = legacy_root / "Datasets" / "stanford_cars" / "stanford_cars" / "cars_train"
    cars_test = legacy_root / "Datasets" / "stanford_cars" / "stanford_cars" / "cars_test"
    raw_drop = legacy_root / "Datasets" / "us_plate_detection" / "oklahoma" / "incoming_raw" / "session_a"
    ocr_standard = legacy_root / "Datasets" / "us_plate_ocr" / "oklahoma" / "synthetic_rendered" / "rendered_20260318_062012"
    ocr_tribal = legacy_root / "Datasets" / "us_plate_ocr" / "oklahoma" / "synthetic_rendered" / "tribal_rendered_20260318_064909"

    for path in (
        cars_train,
        cars_test,
        raw_drop,
        ocr_standard / "train" / "images",
        ocr_standard / "valid" / "images",
        ocr_standard / "test" / "images",
        ocr_tribal / "train" / "images",
        ocr_tribal / "valid" / "images",
        ocr_tribal / "test" / "images",
    ):
        path.mkdir(parents=True, exist_ok=True)

    for target in (
        cars_train / "car_0001.jpg",
        cars_test / "car_1001.jpg",
        raw_drop / "frame_0001.jpg",
        raw_drop / "contact_sheet.jpg",
        raw_drop / "staging_preview.jpg",
        ocr_standard / "train" / "images" / "ocr_0001.png",
        ocr_standard / "valid" / "images" / "ocr_0002.png",
        ocr_standard / "test" / "images" / "ocr_0003.png",
        ocr_tribal / "train" / "images" / "ocr_0101.png",
        ocr_tribal / "valid" / "images" / "ocr_0102.png",
        ocr_tribal / "test" / "images" / "ocr_0103.png",
    ):
        target.write_bytes(b"img")

    for target in (
        ocr_standard / "train" / "labels.csv",
        ocr_standard / "valid" / "labels.csv",
        ocr_standard / "test" / "labels.csv",
        ocr_tribal / "train" / "labels.csv",
        ocr_tribal / "valid" / "labels.csv",
        ocr_tribal / "test" / "labels.csv",
    ):
        target.write_text("image_file,plate_text\nsample.png,ABC123\n", encoding="utf-8")

    output_dir = tmp_path / "manifests"
    result = _run_script(
        "scripts/import_legacy_training_sources.py",
        "--legacy-training-root",
        str(legacy_root),
        "--output-dir",
        str(output_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    files = sorted(path.name for path in output_dir.glob("*.yaml"))
    assert files == [
        "legacy-oklahoma-detection-staging.yaml",
        "legacy-oklahoma-ocr-synthetic-standard.yaml",
        "legacy-oklahoma-ocr-synthetic-tribal.yaml",
        "legacy-stanford-cars-warmstart.yaml",
    ]

    stanford_manifest = load_training_dataset_manifest(output_dir / "legacy-stanford-cars-warmstart.yaml")
    assert stanford_manifest.splits[0].sample_count == 1

    detection_manifest = load_training_dataset_manifest(output_dir / "legacy-oklahoma-detection-staging.yaml")
    assert len(detection_manifest.assets) == 1

    ocr_manifest = load_training_dataset_manifest(output_dir / "legacy-oklahoma-ocr-synthetic-standard.yaml")
    split_counts = {split.split: split.sample_count for split in ocr_manifest.splits}
    assert split_counts[DatasetSplit.train] == 1
    assert split_counts[DatasetSplit.validation] == 1
    assert split_counts[DatasetSplit.holdout] == 1


def test_import_openalpr_us_ocr_dataset_builds_repo_manifest(tmp_path):
    source_root = tmp_path / "openalpr_train_data"
    images_root = source_root / "usimages"
    images_root.mkdir(parents=True)
    for index in range(10):
        (images_root / f"ok{index:03d}.png").write_bytes(b"img")

    (source_root / "groundtruth.csv").write_text(
        "\n".join(
            [
                "ok000.png,abc123",
                "ok001.png,xyz987",
                "ok002.png,12a34",
                "ok003.png,7B8C9D",
                "ok004.png,HELLO1",
                "ok005.png,ROAD42",
                "ok006.png,PLATE7",
                "ok007.png,STATE8",
                "ok008.png,FIELD9",
                "ok009.png,CAPT10",
                "missing.png,NOPE1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "staged_openalpr"
    manifest_path = tmp_path / "openalpr-manifest.yaml"
    result = _run_script(
        "scripts/import_openalpr_us_ocr_dataset.py",
        "--source-root",
        str(source_root),
        "--output-root",
        str(output_root),
        "--manifest-path",
        str(manifest_path),
        "--seed",
        "7",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    manifest = load_training_dataset_manifest(manifest_path)
    split_counts = {split.split: split.sample_count for split in manifest.splits}
    assert split_counts[DatasetSplit.train] == 8
    assert split_counts[DatasetSplit.validation] == 1
    assert split_counts[DatasetSplit.holdout] == 1

    summary = json.loads((output_root / "import_summary.json").read_text(encoding="utf-8"))
    assert summary["missing_source_image_count"] == 1
    assert set(summary["character_set"]).issubset(set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"))

    train_labels = (output_root / "train" / "labels.csv").read_text(encoding="utf-8")
    assert "ABC123" in train_labels
