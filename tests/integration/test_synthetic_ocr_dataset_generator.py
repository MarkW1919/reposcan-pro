from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import yaml

from reposcan_contracts.config.loader import load_training_dataset_manifest
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


def _write_profile(example_name: str, output_root: Path, destination: Path) -> Path:
    source = REPO_ROOT / "configs" / "training" / example_name
    profile = yaml.safe_load(source.read_text(encoding="utf-8"))
    profile["output_root"] = output_root.as_posix()
    destination.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    return destination


def test_synthetic_oklahoma_ocr_generator_prepares_repo_compatible_dataset(tmp_path):
    dataset_root = tmp_path / "synthetic_ok_ocr"
    manifest_path = tmp_path / "synthetic_ok_ocr.yaml"

    generate = _run_script(
        "scripts/generate_synthetic_ok_ocr_dataset.py",
        "--count",
        "18",
        "--output-root",
        str(dataset_root),
        "--manifest-output",
        str(manifest_path),
        "--dataset-name",
        "tmp-synthetic-ok-ocr",
        "--dataset-version",
        "1",
        "--seed",
        "7",
    )
    assert generate.returncode == 0, generate.stdout + generate.stderr

    validate = _run_script(
        "scripts/validate_training_dataset_manifest.py",
        "--manifest",
        str(manifest_path),
        "--verify-files",
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr

    manifest = load_training_dataset_manifest(manifest_path)
    split_counts = {split.split: split.sample_count for split in manifest.splits}
    assert split_counts[DatasetSplit.train] == 14
    assert split_counts[DatasetSplit.validation] == 2
    assert split_counts[DatasetSplit.holdout] == 2

    for split_name in ("train", "validation", "holdout"):
        labels_path = dataset_root / split_name / "labels.csv"
        assert labels_path.exists()
        with labels_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        assert rows
        assert all(row["plate_text"] for row in rows)
        assert all(row["plate_text"].isalnum() for row in rows)

    profile_path = _write_profile(
        "plate-ocr-finetune.yaml",
        tmp_path / "runs",
        tmp_path / "synthetic-ocr-profile.yaml",
    )
    prepare = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "synthetic-ocr-smoke",
        "--allow-pending",
    )
    assert prepare.returncode == 0, prepare.stdout + prepare.stderr
    assert "us_plate_dict.txt" in prepare.stdout
    assert "Preparation complete. Training was not started." in prepare.stdout
