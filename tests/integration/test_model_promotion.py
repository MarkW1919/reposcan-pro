from __future__ import annotations

from pathlib import Path

import yaml

from reposcan_contracts.config.loader import load_model_config
from reposcan_inference.promotion import (
    build_model_artifact_manifest,
    package_promoted_onnx_bundle,
    validate_promoted_model_stack,
)


def _fixture_root() -> Path:
    return Path("ml/inference/fixtures/onnx-runtime")


def _copy_fixture_models(destination: Path) -> dict[str, Path]:
    source_root = _fixture_root()
    mapping = {
        "vehicle_detector": destination / "vehicle-detector.onnx",
        "plate_detector": destination / "plate-detector.onnx",
        "ocr": destination / "ocr.onnx",
        "classifier": destination / "classifier.onnx",
    }
    destination.mkdir(parents=True, exist_ok=True)
    for source_name, target_path in {
        "vehicle-detector.onnx": mapping["vehicle_detector"],
        "plate-detector.onnx": mapping["plate_detector"],
        "ocr.onnx": mapping["ocr"],
        "classifier.onnx": mapping["classifier"],
    }.items():
        target_path.write_bytes((source_root / source_name).read_bytes())
    return mapping


def _write_promoted_config(
    tmp_path: Path,
    artifact_paths: dict[str, Path],
    manifest_paths: dict[str, Path],
    *,
    relative_paths: bool = False,
) -> Path:
    config = yaml.safe_load(Path("configs/models/local-onnx-runtime.yaml").read_text(encoding="utf-8"))
    config["stack_name"] = "tmp-promoted-onnx"
    if relative_paths:
        config["path_base"] = "config_dir"
        config_path = tmp_path / "promoted-onnx.yaml"
        config["vehicle_detector"]["artifact_path"] = Path("artifacts", artifact_paths["vehicle_detector"].name).as_posix()
        config["vehicle_detector"]["artifact_manifest_path"] = Path("manifests", manifest_paths["vehicle_detector"].name).as_posix()
        config["plate_detector"]["artifact_path"] = Path("artifacts", artifact_paths["plate_detector"].name).as_posix()
        config["plate_detector"]["artifact_manifest_path"] = Path("manifests", manifest_paths["plate_detector"].name).as_posix()
        config["ocr"]["artifact_path"] = Path("artifacts", artifact_paths["ocr"].name).as_posix()
        config["ocr"]["artifact_manifest_path"] = Path("manifests", manifest_paths["ocr"].name).as_posix()
        config["classifier"]["artifact_path"] = Path("artifacts", artifact_paths["classifier"].name).as_posix()
        config["classifier"]["artifact_manifest_path"] = Path("manifests", manifest_paths["classifier"].name).as_posix()
    else:
        config["vehicle_detector"]["artifact_path"] = str(artifact_paths["vehicle_detector"])
        config["vehicle_detector"]["artifact_manifest_path"] = str(manifest_paths["vehicle_detector"])
        config["plate_detector"]["artifact_path"] = str(artifact_paths["plate_detector"])
        config["plate_detector"]["artifact_manifest_path"] = str(manifest_paths["plate_detector"])
        config["ocr"]["artifact_path"] = str(artifact_paths["ocr"])
        config["ocr"]["artifact_manifest_path"] = str(manifest_paths["ocr"])
        config["classifier"]["artifact_path"] = str(artifact_paths["classifier"])
        config["classifier"]["artifact_manifest_path"] = str(manifest_paths["classifier"])
        config_path = tmp_path / "promoted-onnx.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_promoted_model_stack_validates_when_manifests_match(tmp_path):
    artifact_paths = _copy_fixture_models(tmp_path / "bundle")
    base_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    assert base_stack.classifier is not None

    manifest_paths = {stage: tmp_path / f"{stage}.manifest.json" for stage in artifact_paths}
    stage_configs = {
        "vehicle_detector": base_stack.vehicle_detector.model_copy(update={"artifact_path": str(artifact_paths["vehicle_detector"])}),
        "plate_detector": base_stack.plate_detector.model_copy(update={"artifact_path": str(artifact_paths["plate_detector"])}),
        "ocr": base_stack.ocr.model_copy(update={"artifact_path": str(artifact_paths["ocr"])}),
        "classifier": base_stack.classifier.model_copy(update={"artifact_path": str(artifact_paths["classifier"])}),
    }

    for stage, manifest_path in manifest_paths.items():
        manifest = build_model_artifact_manifest(
            stage=stage,
            model_config=stage_configs[stage],
            exported_at_utc="2026-03-22T19:00:00Z",
            source_run_id="run_demo_001",
            dataset_manifests=["data/manifests/night-holdout.yaml"],
            export_tool="torch.onnx.export",
            export_tool_version="2.7.0",
            opset_version=17,
            precision="fp16",
            target_runtime="onnxruntime",
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    config_path = _write_promoted_config(tmp_path, artifact_paths, manifest_paths)
    promoted_stack = load_model_config(config_path)
    report = validate_promoted_model_stack(promoted_stack)

    assert report.runtime_ready is True
    assert report.ready is True
    assert report.error_count == 0


def test_promoted_model_stack_validates_relative_bundle_paths(tmp_path):
    bundle_root = tmp_path / "packaged"
    artifact_paths = _copy_fixture_models(bundle_root / "artifacts")
    base_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    assert base_stack.classifier is not None

    manifest_paths = {stage: bundle_root / "manifests" / f"{stage}.manifest.json" for stage in artifact_paths}
    for path in manifest_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    stage_configs = {
        "vehicle_detector": base_stack.vehicle_detector.model_copy(update={"artifact_path": "artifacts/vehicle-detector.onnx"}),
        "plate_detector": base_stack.plate_detector.model_copy(update={"artifact_path": "artifacts/plate-detector.onnx"}),
        "ocr": base_stack.ocr.model_copy(update={"artifact_path": "artifacts/ocr.onnx"}),
        "classifier": base_stack.classifier.model_copy(update={"artifact_path": "artifacts/classifier.onnx"}),
    }

    for stage, manifest_path in manifest_paths.items():
        manifest = build_model_artifact_manifest(
            stage=stage,
            model_config=stage_configs[stage],
            resolved_artifact_path=artifact_paths[stage],
            exported_at_utc="2026-03-22T20:00:00Z",
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    config_path = _write_promoted_config(bundle_root, artifact_paths, manifest_paths, relative_paths=True)
    promoted_stack = load_model_config(config_path)
    report = validate_promoted_model_stack(promoted_stack)

    assert report.runtime_ready is True
    assert report.ready is True
    assert report.error_count == 0


def test_promoted_model_stack_rejects_sha_mismatch(tmp_path):
    artifact_paths = _copy_fixture_models(tmp_path / "bundle")
    base_stack = load_model_config("configs/models/local-onnx-runtime.yaml")
    assert base_stack.classifier is not None
    manifest_paths = {stage: tmp_path / f"{stage}.manifest.json" for stage in artifact_paths}
    stage_configs = {
        "vehicle_detector": base_stack.vehicle_detector.model_copy(update={"artifact_path": str(artifact_paths["vehicle_detector"])}),
        "plate_detector": base_stack.plate_detector.model_copy(update={"artifact_path": str(artifact_paths["plate_detector"])}),
        "ocr": base_stack.ocr.model_copy(update={"artifact_path": str(artifact_paths["ocr"])}),
        "classifier": base_stack.classifier.model_copy(update={"artifact_path": str(artifact_paths["classifier"])}),
    }

    for stage, manifest_path in manifest_paths.items():
        manifest = build_model_artifact_manifest(
            stage=stage,
            model_config=stage_configs[stage],
            exported_at_utc="2026-03-22T19:00:00Z",
        )
        if stage == "ocr":
            manifest = manifest.model_copy(update={"artifact_sha256": "0" * 64})
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    config_path = _write_promoted_config(tmp_path, artifact_paths, manifest_paths)
    promoted_stack = load_model_config(config_path)
    report = validate_promoted_model_stack(promoted_stack)

    assert report.ready is False
    assert any("sha256" in issue.message for stage in report.stages for issue in stage.issues)


def test_package_promoted_onnx_bundle_creates_valid_external_bundle(tmp_path):
    source_stack = load_model_config("configs/models/local-onnx-runtime.yaml")

    report = package_promoted_onnx_bundle(
        source_stack,
        output_dir=tmp_path / "exported-bundle",
        bundle_name="fixture-promoted-export",
        exported_at_utc="2026-03-22T21:00:00Z",
        source_run_id="fixture_run_001",
        export_tool="reposcan.package_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=13,
        precision="fp32",
        target_runtime="onnxruntime",
    )

    assert report.ready is True
    assert Path(report.config_path).exists()
    assert (tmp_path / "exported-bundle" / "artifacts" / "vehicle-detector.onnx").exists()
    assert (tmp_path / "exported-bundle" / "manifests" / "vehicle_detector.manifest.json").exists()

    packaged_stack = load_model_config(report.config_path)
    validation = validate_promoted_model_stack(packaged_stack)

    assert packaged_stack.path_base.value == "config_dir"
    assert validation.ready is True
