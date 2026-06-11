from __future__ import annotations

from pathlib import Path
from shutil import copy2

from reposcan_contracts.config.loader import load_deployment_config, load_model_config
from reposcan_inference import package_promoted_onnx_bundle, validate_deployment_runtime_bundle
from reposcan_inference.promotion import build_model_artifact_manifest


def _fixture_root() -> Path:
    return Path("ml/inference/fixtures/onnx-runtime")


def _build_tensorrt_bundle(
    bundle_root: Path,
    *,
    compute_capability: str = "8.7",
    tensorrt_version: str = "10.0.1",
) -> Path:
    artifacts_dir = bundle_root / "artifacts"
    manifests_dir = bundle_root / "manifests"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    copy2("configs/models/promoted-tensorrt-template.yaml", bundle_root / "promoted-tensorrt.yaml")

    source_root = _fixture_root()
    copies = {
        "vehicle_detector": ("vehicle-detector.onnx", "yolov8n-vehicle.engine"),
        "plate_detector": ("plate-detector.onnx", "yolov8n-plate.engine"),
        "ocr": ("ocr.onnx", "lprnet-v1.engine"),
        "classifier": ("classifier.onnx", "vehicle-attr-v1.engine"),
    }
    for source_name, target_name in copies.values():
        copy2(source_root / source_name, artifacts_dir / target_name)

    stack = load_model_config(bundle_root / "promoted-tensorrt.yaml")
    assert stack.classifier is not None
    stage_configs = {
        "vehicle_detector": stack.vehicle_detector,
        "plate_detector": stack.plate_detector,
        "ocr": stack.ocr,
        "classifier": stack.classifier,
    }
    for stage, model_config in stage_configs.items():
        manifest = build_model_artifact_manifest(
            stage=stage,
            model_config=model_config,
            resolved_artifact_path=stack.resolve_artifact_path(model_config.artifact_path),
            exported_at_utc="2026-03-22T23:00:00Z",
            export_tool="trtexec",
            export_tool_version="10.0",
            precision="fp16",
            target_runtime="tensorrt",
            cuda_version="12.2",
            tensorrt_version=tensorrt_version,
            device_compute_capability=compute_capability,
            engine_profile="opt",
            workspace_megabytes=1024,
        )
        manifest_path = stack.resolve_artifact_path(model_config.artifact_manifest_path or "")
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return bundle_root / "promoted-tensorrt.yaml"


def test_validate_edge_runtime_bundle_accepts_local_onnx_bundle_for_local_dev(tmp_path):
    source_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    deployment = load_deployment_config("configs/deployments/local-dev.yaml")
    package_report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "onnx-bundle",
        bundle_name="fixture-local-dev",
        exported_at_utc="2026-03-22T23:10:00Z",
        source_run_id="fixture_local_dev",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    stack = load_model_config(package_report.config_path)
    report = validate_deployment_runtime_bundle(stack, deployment)

    assert report.runtime_ready is True
    assert report.promotion_ready is True
    assert report.ready is True
    assert report.error_count == 0


def test_validate_edge_runtime_bundle_accepts_tensorrt_bundle_for_jetson_orin(tmp_path):
    deployment = load_deployment_config("configs/deployments/jetson-orin-edge.yaml")
    config_path = _build_tensorrt_bundle(tmp_path / "jetson-bundle")
    stack = load_model_config(config_path)

    report = validate_deployment_runtime_bundle(stack, deployment)

    assert report.runtime_ready is True
    assert report.promotion_ready is True
    assert report.ready is True
    assert report.error_count == 0


def test_validate_edge_runtime_bundle_accepts_tensorrt_bundle_for_jetson_orin_nano_super(tmp_path):
    deployment = load_deployment_config("configs/deployments/jetson-orin-nano-super.yaml")
    config_path = _build_tensorrt_bundle(tmp_path / "nano-super-bundle")
    stack = load_model_config(config_path)

    report = validate_deployment_runtime_bundle(stack, deployment)

    assert report.runtime_ready is True
    assert report.promotion_ready is True
    assert report.ready is True
    assert report.error_count == 0


def test_validate_edge_runtime_bundle_rejects_compute_capability_mismatch(tmp_path):
    deployment = load_deployment_config("configs/deployments/jetson-orin-edge.yaml")
    config_path = _build_tensorrt_bundle(tmp_path / "jetson-bundle", compute_capability="7.2")
    stack = load_model_config(config_path)

    report = validate_deployment_runtime_bundle(stack, deployment)

    assert report.ready is False
    assert any("device_compute_capability" in issue.message for issue in report.issues)
