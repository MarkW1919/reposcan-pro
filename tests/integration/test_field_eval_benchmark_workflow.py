from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

from reposcan_contracts.config.loader import load_benchmark_manifest, load_model_config, load_training_dataset_manifest
from reposcan_inference import build_benchmark_manifest_from_eval_holdout, package_promoted_onnx_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_demo_image(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 72), color=color).save(path, format="JPEG")


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_eval_manifest(path: Path, storage_root: Path) -> None:
    manifest = {
        "dataset_name": "legacy-oklahoma-field-eval-reviewed",
        "dataset_version": "2026-03-23",
        "task": "plate_detection",
        "format": "eval_holdout",
        "storage_root": str(storage_root),
        "review_status": "approved",
        "provenance": {
            "source_name": "Legacy Oklahoma reviewed eval",
            "source_kind": "field_capture",
            "license_tier": "internal",
            "license_name": "internal field capture",
            "license_reference": "internal://reposcan/legacy-oklahoma-eval",
            "region": "us-ok",
        },
        "annotation_review": {
            "reviewer": "qa_eval_01",
            "reviewed_at_utc": "2026-03-23T12:00:00Z",
            "accepted_tasks": ["plate_detection"],
        },
        "assets": [
            {
                "asset_id": "eval_0001",
                "relative_path": "images/field_eval/eval_0001.jpg",
                "capture_session_id": "session_ok_night_01",
                "lighting_conditions": ["night", "ir_assisted"],
                "distance_band": "long_range",
                "annotations": ["plate_detection"],
                "expected_plate_text": "6BZN220",
                "vehicle_color": "white",
                "vehicle_make": "toyota",
                "tags": ["legacy_import"],
                "field_eval_candidate": True,
            },
            {
                "asset_id": "eval_0002",
                "relative_path": "images/field_eval/eval_0002.jpg",
                "capture_session_id": "session_ok_night_02",
                "lighting_conditions": ["night"],
                "annotations": ["plate_detection"],
                "expected_plate_text": "6BZN221",
                "vehicle_color": "white",
                "vehicle_make": "toyota",
                "tags": ["reviewed"],
                "field_eval_candidate": True,
            },
        ],
        "splits": [
            {
                "split": "field_eval",
                "relative_path": "images/field_eval",
                "label_path": "labels/field_eval",
                "sample_count": 2,
                "capture_session_ids": ["session_ok_night_01", "session_ok_night_02"],
                "tags": ["low_light", "long_range"],
            }
        ],
    }
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def test_build_benchmark_manifest_from_eval_holdout_derives_tags(tmp_path):
    storage_root = tmp_path / "eval-data"
    _write_demo_image(storage_root / "images" / "field_eval" / "eval_0001.jpg", color=(240, 240, 240))
    _write_demo_image(storage_root / "images" / "field_eval" / "eval_0002.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "field-eval.yaml"
    _write_eval_manifest(manifest_path, storage_root)

    training_manifest = load_training_dataset_manifest(manifest_path)
    benchmark_manifest = build_benchmark_manifest_from_eval_holdout(
        repo_root=REPO_ROOT,
        dataset_manifest=training_manifest,
        dataset_manifest_path=manifest_path,
    )

    assert benchmark_manifest.benchmark_name == "legacy-oklahoma-field-eval-reviewed-benchmark"
    assert benchmark_manifest.camera_id == "cam_eval_legacy_oklahoma_field_eval_reviewed"
    assert benchmark_manifest.frames[0].expected_plate_text == "6BZN220"
    assert "low_light" in benchmark_manifest.frames[0].tags
    assert "long_range" in benchmark_manifest.frames[0].tags
    assert benchmark_manifest.frames[1].expected_plate_text == "6BZN221"


def test_build_benchmark_manifest_requires_approved_eval_holdout(tmp_path):
    storage_root = tmp_path / "eval-data"
    _write_demo_image(storage_root / "images" / "field_eval" / "eval_0001.jpg", color=(240, 240, 240))
    _write_demo_image(storage_root / "images" / "field_eval" / "eval_0002.jpg", color=(240, 240, 240))

    manifest_path = tmp_path / "field-eval.yaml"
    _write_eval_manifest(manifest_path, storage_root)
    manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest_data["review_status"] = "pending"
    manifest_data.pop("annotation_review", None)
    manifest_path.write_text(yaml.safe_dump(manifest_data, sort_keys=False), encoding="utf-8")

    training_manifest = load_training_dataset_manifest(manifest_path)
    with pytest.raises(ValueError, match="approved eval-holdout dataset manifest"):
        build_benchmark_manifest_from_eval_holdout(repo_root=REPO_ROOT, dataset_manifest=training_manifest)


def test_benchmark_script_accepts_dataset_manifest_and_writes_report(tmp_path):
    storage_root = tmp_path / "eval-data"
    _write_demo_image(storage_root / "images" / "field_eval" / "eval_0001.jpg", color=(240, 240, 240))
    _write_demo_image(storage_root / "images" / "field_eval" / "eval_0002.jpg", color=(240, 240, 240))

    dataset_manifest = tmp_path / "field-eval.yaml"
    _write_eval_manifest(dataset_manifest, storage_root)

    source_stack = load_model_config(REPO_ROOT / "configs" / "models" / "local-onnx-runtime.yaml")
    package_report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "onnx-bundle",
        bundle_name="field-eval-benchmark-bundle",
        exported_at_utc="2026-03-23T15:00:00Z",
        source_run_id="field_eval_benchmark_001",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    derived_benchmark = tmp_path / "derived-benchmark.yaml"
    report_output = tmp_path / "benchmark-report.json"

    result = _run_script(
        "scripts/benchmark_promoted_bundle.py",
        "--model-config",
        str(package_report.config_path),
        "--dataset-manifest",
        str(dataset_manifest),
        "--deployment-config",
        str(REPO_ROOT / "configs" / "deployments" / "local-dev.yaml"),
        "--derived-benchmark-output",
        str(derived_benchmark),
        "--report-output",
        str(report_output),
        "--json",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert derived_benchmark.exists()
    assert report_output.exists()

    derived_manifest = load_benchmark_manifest(derived_benchmark)
    assert derived_manifest.benchmark_name == "legacy-oklahoma-field-eval-reviewed-benchmark"
    assert any("low_light" in frame.tags for frame in derived_manifest.frames)

    report = json.loads(report_output.read_text(encoding="utf-8"))
    assert report["source_dataset_name"] == "legacy-oklahoma-field-eval-reviewed"
    assert report["overall"]["frames"] == 2
    assert report["overall"]["average_latency_ms"] is not None
    assert report["validation"]["deployment_ready"] is True
    assert report["subsets"]["long_range"]["frames"] == 1
    assert report["subsets"]["low_light"]["frames"] == 2
