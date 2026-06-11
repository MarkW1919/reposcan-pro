from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from reposcan_contracts.config.loader import load_model_config
from reposcan_inference import validate_promoted_model_stack


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_assemble_promoted_onnx_bundle_from_exported_stage_artifacts(tmp_path):
    source_root = REPO_ROOT / "ml" / "inference" / "fixtures" / "onnx-runtime"
    exports_root = tmp_path / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)

    artifact_map = {
        "vehicle_detector": exports_root / "vehicle-detector-export.onnx",
        "plate_detector": exports_root / "plate-detector-export.onnx",
        "ocr": exports_root / "ocr-export.onnx",
        "classifier": exports_root / "classifier-export.onnx",
    }
    for source_name, destination in {
        "vehicle-detector.onnx": artifact_map["vehicle_detector"],
        "plate-detector.onnx": artifact_map["plate_detector"],
        "ocr.onnx": artifact_map["ocr"],
        "classifier.onnx": artifact_map["classifier"],
    }.items():
        destination.write_bytes((source_root / source_name).read_bytes())

    result = _run_script(
        "scripts/assemble_promoted_onnx_bundle.py",
        "--template-model-config",
        "configs/models/local-onnx-runtime.yaml",
        "--vehicle-detector-artifact",
        str(artifact_map["vehicle_detector"]),
        "--plate-detector-artifact",
        str(artifact_map["plate_detector"]),
        "--ocr-artifact",
        str(artifact_map["ocr"]),
        "--classifier-artifact",
        str(artifact_map["classifier"]),
        "--output-dir",
        str(tmp_path / "promoted-bundle"),
        "--bundle-name",
        "exported-onnx-smoke",
        "--source-run-id",
        "run_exported_onnx_001",
        "--dataset-manifest",
        "configs/datasets/example-field-eval-holdout.yaml",
        "--export-tool",
        "reposcan.training.export",
        "--export-tool-version",
        "0.1.0",
        "--opset-version",
        "17",
        "--precision",
        "fp32",
        "--target-runtime",
        "onnxruntime",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    config_path = tmp_path / "promoted-bundle" / "promoted-onnx.yaml"
    assert config_path.exists()
    assert (tmp_path / "promoted-bundle" / "artifacts" / "vehicle-detector-export.onnx").exists()
    assert (tmp_path / "promoted-bundle" / "manifests" / "vehicle_detector.manifest.json").exists()

    promoted_stack = load_model_config(config_path)
    validation = validate_promoted_model_stack(promoted_stack)

    assert validation.ready is True
    manifest = json.loads((tmp_path / "promoted-bundle" / "manifests" / "vehicle_detector.manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_run_id"] == "run_exported_onnx_001"
    assert manifest["export_tool"] == "reposcan.training.export"
    assert manifest["target_runtime"] == "onnxruntime"
