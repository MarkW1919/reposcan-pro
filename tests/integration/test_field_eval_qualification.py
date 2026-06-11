from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_demo_image(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 72), color=color).save(path, format="JPEG")


def _write_eval_manifest(path: Path, storage_root: Path) -> None:
    assets = []
    image_specs = [
        ("eval_0001", "session_a", ["night", "ir_assisted"], "long_range", ["low_light", "long_range"], "6BZN220"),
        ("eval_0002", "session_a", ["night"], None, ["low_light"], "6BZN221"),
        ("eval_0003", "session_b", ["daylight"], "long_range", ["long_range"], "6BZN222"),
        ("eval_0004", "session_b", ["night"], None, ["low_light"], "6BZN223"),
        ("eval_0005", "session_c", ["daylight"], "long_range", ["long_range"], "6BZN224"),
        ("eval_0006", "session_d", ["night"], None, ["low_light"], "6BZN225"),
    ]
    for asset_id, session_id, lighting_conditions, distance_band, tags, plate_text in image_specs:
        assets.append(
            {
                "asset_id": asset_id,
                "relative_path": f"images/field_eval/{asset_id}.jpg",
                "capture_session_id": session_id,
                "lighting_conditions": lighting_conditions,
                "distance_band": distance_band,
                "annotations": ["plate_detection"],
                "expected_plate_text": plate_text,
                "vehicle_color": "white",
                "vehicle_make": "toyota",
                "tags": tags,
                "field_eval_candidate": True,
            }
        )

    manifest = {
        "dataset_name": "qualified-field-eval",
        "dataset_version": "2026-03-24",
        "task": "plate_detection",
        "format": "eval_holdout",
        "storage_root": str(storage_root),
        "review_status": "approved",
        "provenance": {
            "source_name": "Qualified field eval",
            "source_kind": "field_capture",
            "license_tier": "internal",
            "license_name": "internal field capture",
            "license_reference": "internal://reposcan/qualified-field-eval",
            "region": "us-ok",
        },
        "annotation_review": {
            "reviewer": "qa_eval_02",
            "reviewed_at_utc": "2026-03-24T08:00:00Z",
            "accepted_tasks": ["plate_detection"],
        },
        "assets": assets,
        "splits": [
            {
                "split": "field_eval",
                "relative_path": "images/field_eval",
                "label_path": "labels/field_eval",
                "sample_count": len(assets),
                "capture_session_ids": ["session_a", "session_b", "session_c", "session_d"],
                "tags": ["low_light", "long_range"],
            }
        ],
    }
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def test_field_eval_qualification_succeeds_with_relaxed_thresholds(tmp_path):
    storage_root = tmp_path / "eval-data"
    for index in range(1, 7):
        _write_demo_image(storage_root / "images" / "field_eval" / f"eval_{index:04d}.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "qualified-field-eval.yaml"
    _write_eval_manifest(manifest_path, storage_root)
    report_output = tmp_path / "qualification-report.json"

    result = _run_script(
        "scripts/qualify_field_eval_dataset.py",
        "--dataset-manifest",
        str(manifest_path),
        "--min-total-assets",
        "6",
        "--min-benchmark-ready-assets",
        "6",
        "--min-long-range-assets",
        "3",
        "--min-low-light-assets",
        "4",
        "--min-long-range-sessions",
        "2",
        "--min-low-light-sessions",
        "2",
        "--verify-files",
        "--report-output",
        str(report_output),
        "--json",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_output.read_text(encoding="utf-8"))
    assert report["qualified"] is True
    assert report["total_assets"] == 6
    assert report["benchmark_ready_assets"] == 6
    assert report["subsets"]["long_range"]["assets"] == 3
    assert report["subsets"]["low_light"]["assets"] == 4
    assert report["missing_file_assets"] == 0


def test_field_eval_qualification_fails_default_gate_for_example_manifest(tmp_path):
    report_output = tmp_path / "example-qualification-report.json"
    result = _run_script(
        "scripts/qualify_field_eval_dataset.py",
        "--dataset-manifest",
        str(REPO_ROOT / "configs" / "datasets" / "example-field-eval-holdout.yaml"),
        "--report-output",
        str(report_output),
        "--json",
    )

    assert result.returncode == 1
    report = json.loads(report_output.read_text(encoding="utf-8"))
    assert report["qualified"] is False
    messages = [issue["message"] for issue in report["issues"]]
    assert any("total assets 1 is below required minimum 10" in message for message in messages)
    assert any("long_range assets 1 is below required minimum 4" in message for message in messages)
    assert any("low_light assets 1 is below required minimum 4" in message for message in messages)
