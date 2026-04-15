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


def _write_development_manifest(path: Path) -> None:
    assets = []
    specs = [
        ("asset_0001", "session_night_a", "images/train/asset_0001.jpg", ["night"], "long_range", ["low_light", "long_range"]),
        ("asset_0002", "session_night_a", "images/train/asset_0002.jpg", ["night"], "medium", ["low_light"]),
        ("asset_0003", "session_day_a", "images/train/asset_0003.jpg", ["daylight"], "medium", ["daytime"]),
        ("asset_0004", "session_day_b", "images/train/asset_0004.jpg", ["daylight"], "medium", ["daytime"]),
        ("asset_0005", "session_day_b", "images/train/asset_0005.jpg", ["daylight"], "medium", ["daytime"]),
        ("asset_0006", "session_val_a", "images/validation/asset_0006.jpg", ["dusk"], "long_range", ["long_range"]),
        ("asset_0007", "session_val_a", "images/validation/asset_0007.jpg", ["daylight"], "medium", ["daytime"]),
        ("asset_0008", "session_holdout_a", "images/holdout/asset_0008.jpg", ["night"], "long_range", ["low_light", "long_range"]),
        ("asset_0009", "session_holdout_b", "images/holdout/asset_0009.jpg", ["daylight"], "medium", ["daytime"]),
        ("asset_0010", "session_holdout_b", "images/holdout/asset_0010.jpg", ["daylight"], "medium", ["daytime"]),
    ]
    for asset_id, session_id, relative_path, lighting, distance_band, tags in specs:
        assets.append(
            {
                "asset_id": asset_id,
                "relative_path": relative_path,
                "capture_session_id": session_id,
                "lighting_conditions": lighting,
                "distance_band": distance_band,
                "annotations": ["plate_detection"],
                "tags": tags,
            }
        )

    manifest = {
        "dataset_name": "development-oklahoma-plate-detection",
        "dataset_version": "2026-04-15",
        "task": "plate_detection",
        "format": "yolo_detection",
        "storage_root": "data/curated/dev-oklahoma-plate-detection",
        "review_status": "approved",
        "provenance": {
            "source_name": "development-oklahoma-capture",
            "source_kind": "field_capture",
            "license_tier": "internal",
            "license_name": "internal field capture",
            "license_reference": "internal://reposcan/development-oklahoma-capture",
            "region": "us-ok",
        },
        "annotation_review": {
            "reviewer": "qa_dev_01",
            "reviewed_at_utc": "2026-04-15T00:00:00Z",
            "accepted_tasks": ["plate_detection"],
        },
        "assets": assets,
        "splits": [
            {
                "split": "train",
                "relative_path": "images/train",
                "label_path": "labels/train",
                "sample_count": 5,
                "capture_session_ids": ["session_night_a", "session_day_a", "session_day_b"],
            },
            {
                "split": "validation",
                "relative_path": "images/validation",
                "label_path": "labels/validation",
                "sample_count": 2,
                "capture_session_ids": ["session_val_a"],
            },
            {
                "split": "holdout",
                "relative_path": "images/holdout",
                "label_path": "labels/holdout",
                "sample_count": 3,
                "capture_session_ids": ["session_holdout_a", "session_holdout_b"],
            },
        ],
    }
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def test_dataset_readiness_development_gate_passes(tmp_path):
    manifest_path = tmp_path / "dev-dataset.yaml"
    report_path = tmp_path / "report.json"
    _write_development_manifest(manifest_path)

    result = _run_script(
        "scripts/audit_training_dataset_readiness.py",
        "--dataset-manifest",
        str(manifest_path),
        "--level",
        "development",
        "--report-output",
        str(report_path),
        "--json",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ready"] is True
    assert report["policy_name"] == "development"
    assert report["split_samples"] == {"train": 5, "validation": 2, "holdout": 3}


def test_dataset_readiness_commercial_gate_fails_example_fixture(tmp_path):
    report_path = tmp_path / "commercial-report.json"

    result = _run_script(
        "scripts/audit_training_dataset_readiness.py",
        "--dataset-manifest",
        "configs/datasets/example-curated-plate-detection.yaml",
        "--level",
        "oklahoma-commercial",
        "--report-output",
        str(report_path),
        "--json",
    )

    assert result.returncode == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ready"] is False
    messages = [issue["message"] for issue in report["issues"]]
    assert any("train samples 1 is below required minimum 35000" in message for message in messages)
    assert any("asset tag 'vehicle_class:pickup' count 0 is below required minimum 10000" in message for message in messages)
