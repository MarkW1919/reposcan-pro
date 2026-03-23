from __future__ import annotations

import pytest
from pydantic import ValidationError

from reposcan_contracts.model_artifact import ModelArtifactManifest


def _manifest_payload() -> dict:
    return {
        "stage": "vehicle_detector",
        "model_name": "yolov8n-vehicle",
        "backend": "onnx",
        "artifact_path": "artifacts/models/promoted/example/yolov8n-vehicle.onnx",
        "artifact_sha256": "a" * 64,
        "exported_at_utc": "2026-03-22T18:00:00Z",
        "input_width": 640,
        "input_height": 640,
        "source_run_id": "run_20260322_01",
        "dataset_manifests": ["data/manifests/night-holdout.yaml"],
        "export_tool": "torch.onnx.export",
        "export_tool_version": "2.7.0",
        "opset_version": 17,
        "precision": "fp16",
        "target_runtime": "onnxruntime",
    }


def test_model_artifact_manifest_roundtrip():
    manifest = ModelArtifactManifest.model_validate(_manifest_payload())

    restored = ModelArtifactManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest


def test_model_artifact_manifest_requires_positive_input_shape():
    payload = _manifest_payload()
    payload["input_width"] = 0

    with pytest.raises(ValidationError):
        ModelArtifactManifest.model_validate(payload)


def test_model_artifact_manifest_requires_sha256_hex_digest():
    payload = _manifest_payload()
    payload["artifact_sha256"] = "not-a-sha256"

    with pytest.raises(ValidationError):
        ModelArtifactManifest.model_validate(payload)
