from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml
from PIL import Image


_FIXED_TIMESTAMP = "2026-03-24T18:00:00Z"

_FIXTURE_IMAGE_SPECS: list[tuple[str, tuple[int, int, int]]] = [
    ("fixture_eval_0001", (236, 236, 236)),
    ("fixture_eval_0002", (232, 232, 232)),
    ("fixture_eval_0003", (240, 240, 240)),
    ("fixture_eval_0004", (228, 228, 228)),
    ("fixture_eval_0005", (224, 224, 224)),
    ("fixture_eval_0006", (242, 242, 242)),
    ("fixture_eval_0007", (216, 216, 216)),
    ("fixture_eval_0008", (220, 220, 220)),
    ("fixture_eval_0009", (238, 238, 238)),
    ("fixture_eval_0010", (214, 214, 214)),
]


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "apps" / "api" / "src",
        repo_root / "services" / "storage" / "src",
        repo_root / "services" / "capture" / "src",
        repo_root / "services" / "preprocessing" / "src",
        repo_root / "services" / "inference" / "src",
        repo_root / "services" / "tracking" / "src",
        repo_root / "services" / "alerting" / "src",
        repo_root / "ml" / "training" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible Section 4 inference-runtime fixture bundles and evidence reports.",
    )
    parser.add_argument("--output-root", default="ml/inference/fixtures")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def _rounded_metrics(data: dict) -> dict:
    rounded = dict(data)
    for key in (
        "exact_match_rate",
        "character_accuracy",
        "color_accuracy",
        "make_accuracy",
        "average_latency_ms",
        "p95_latency_ms",
        "max_latency_ms",
        "average_vehicles_per_frame",
        "average_plates_per_frame",
    ):
        if key in rounded:
            rounded[key] = _round_float(rounded.get(key))
    return rounded


def _ensure_fixture_images(output_root: Path) -> None:
    images_root = output_root / "runtime-benchmark-holdout" / "images" / "field_eval"
    images_root.mkdir(parents=True, exist_ok=True)
    for image_name, color in _FIXTURE_IMAGE_SPECS:
        image_path = images_root / f"{image_name}.jpg"
        Image.new("RGB", (128, 72), color=color).save(image_path, format="JPEG")


def _build_promoted_tensorrt_bundle(repo_root: Path, output_root: Path) -> Path:
    from reposcan_contracts.config.loader import load_model_config
    from reposcan_inference import build_model_artifact_manifest, validate_deployment_runtime_bundle

    bundle_root = output_root / "promoted-tensorrt-runtime"
    artifacts_dir = bundle_root / "artifacts"
    manifests_dir = bundle_root / "manifests"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    source_root = repo_root / "ml" / "inference" / "fixtures" / "onnx-runtime"
    artifact_names = {
        "vehicle_detector": "yolov8n-vehicle.engine",
        "plate_detector": "yolov8n-plate.engine",
        "ocr": "lprnet-v1.engine",
        "classifier": "vehicle-attr-v1.engine",
    }
    source_names = {
        "vehicle_detector": "vehicle-detector.onnx",
        "plate_detector": "plate-detector.onnx",
        "ocr": "ocr.onnx",
        "classifier": "classifier.onnx",
    }
    for stage, filename in artifact_names.items():
        (artifacts_dir / filename).write_bytes((source_root / source_names[stage]).read_bytes())

    config_data = yaml.safe_load((repo_root / "configs" / "models" / "promoted-tensorrt-template.yaml").read_text(encoding="utf-8"))
    config_data["stack_name"] = "fixture-promoted-tensorrt-runtime"
    config_path = bundle_root / "promoted-tensorrt.yaml"
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    model_stack = load_model_config(config_path)
    for stage_name, stage_config in [
        ("vehicle_detector", model_stack.vehicle_detector),
        ("plate_detector", model_stack.plate_detector),
        ("ocr", model_stack.ocr),
        ("classifier", model_stack.classifier),
    ]:
        if stage_config is None:
            continue
        manifest = build_model_artifact_manifest(
            stage=stage_name,
            model_config=stage_config,
            resolved_artifact_path=model_stack.resolve_artifact_path(stage_config.artifact_path),
            exported_at_utc=_FIXED_TIMESTAMP,
            source_run_id="fixture_tensorrt_export_001",
            source_checkpoint_ref=f"{stage_name}_best.engine",
            dataset_manifests=["configs/datasets/runtime-benchmark-qualified-holdout.yaml"],
            export_tool="trtexec",
            export_tool_version="10.0",
            precision="fp16",
            target_runtime="tensorrt",
            cuda_version="12.2",
            tensorrt_version="10.0.1",
            device_compute_capability="8.7",
            engine_profile="opt",
            workspace_megabytes=1024,
            notes="Contract-validation TensorRT fixture bundle for Section 4 evidence.",
        )
        manifest_path = model_stack.resolve_artifact_path(stage_config.artifact_manifest_path or "")
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    return config_path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_deployment_config, load_model_config, load_training_dataset_manifest
    from reposcan_inference import (
        InferenceService,
        benchmark_promoted_model,
        build_benchmark_manifest_from_eval_holdout,
        package_exported_onnx_bundle,
        validate_deployment_runtime_bundle,
    )
    from reposcan_training import qualify_field_eval_dataset

    args = parse_args()
    output_root = (repo_root / args.output_root).resolve() if not Path(args.output_root).is_absolute() else Path(args.output_root).resolve()
    if output_root.exists() and args.overwrite:
        for child in ("promoted-onnx-runtime", "promoted-tensorrt-runtime", "runtime-benchmark-holdout", "reports"):
            target = output_root / child
            if target.exists():
                shutil.rmtree(target)

    _ensure_fixture_images(output_root)

    onnx_bundle_root = output_root / "promoted-onnx-runtime"
    source_root = repo_root / "ml" / "inference" / "fixtures" / "onnx-runtime"
    onnx_report = package_exported_onnx_bundle(
        load_model_config(repo_root / "configs" / "models" / "local-onnx-runtime.yaml"),
        vehicle_detector_artifact=source_root / "vehicle-detector.onnx",
        plate_detector_artifact=source_root / "plate-detector.onnx",
        ocr_artifact=source_root / "ocr.onnx",
        classifier_artifact=source_root / "classifier.onnx",
        output_dir=onnx_bundle_root,
        bundle_name="fixture-promoted-onnx-runtime",
        exported_at_utc=_FIXED_TIMESTAMP,
        source_run_id="fixture_onnx_export_001",
        source_checkpoint_ref="fixture_onnx_runtime_checkpoint",
        dataset_manifests=["configs/datasets/runtime-benchmark-qualified-holdout.yaml"],
        export_tool="reposcan.assemble_promoted_onnx_bundle",
        export_tool_version="0.1.0",
        opset_version=17,
        precision="fp32",
        target_runtime="onnxruntime",
        notes="Promoted ONNX fixture bundle for Section 4 runtime evidence.",
    )
    if not onnx_report.ready:
        raise RuntimeError("fixture promoted ONNX bundle failed validation")

    tensorrt_config_path = _build_promoted_tensorrt_bundle(repo_root, output_root)

    dataset_manifest_path = repo_root / "configs" / "datasets" / "runtime-benchmark-qualified-holdout.yaml"
    dataset_manifest = load_training_dataset_manifest(dataset_manifest_path)

    qualification_report = qualify_field_eval_dataset(repo_root=repo_root, manifest=dataset_manifest).model_copy(
        update={"generated_at_utc": _FIXED_TIMESTAMP}
    )

    local_deployment = load_deployment_config(repo_root / "configs" / "deployments" / "local-dev.yaml")
    onnx_stack = load_model_config(onnx_bundle_root / "promoted-onnx.yaml")
    benchmark_manifest = build_benchmark_manifest_from_eval_holdout(
        repo_root=repo_root,
        dataset_manifest=dataset_manifest,
        dataset_manifest_path=Path("configs/datasets/runtime-benchmark-qualified-holdout.yaml"),
        benchmark_name="runtime-benchmark-qualified-holdout",
        camera_id="cam_eval_runtime_benchmark_fixture",
        description="Qualified internal fixture holdout used to prove Section 4 promoted-runtime benchmark plumbing.",
    )
    inference_service = InferenceService.from_config_paths(
        model_config_path=onnx_bundle_root / "promoted-onnx.yaml",
        pipeline_config_path=repo_root / "configs" / "pipelines" / "default-edge.yaml",
    )
    benchmark_report = benchmark_promoted_model(
        inference_service,
        benchmark_manifest,
        deployment=local_deployment,
        source_dataset_manifest=dataset_manifest,
    )
    benchmark_report_dict = benchmark_report.model_dump(mode="json")
    benchmark_report_dict["generated_at_utc"] = _FIXED_TIMESTAMP
    benchmark_report_dict["source_dataset_manifest_path"] = "configs/datasets/runtime-benchmark-qualified-holdout.yaml"
    benchmark_report_dict["overall"] = _rounded_metrics(benchmark_report_dict["overall"])
    benchmark_report_dict["subsets"] = {
        name: _rounded_metrics(metrics) for name, metrics in benchmark_report_dict["subsets"].items()
    }

    onnx_deployment_report = validate_deployment_runtime_bundle(onnx_stack, local_deployment)
    tensorrt_stack = load_model_config(tensorrt_config_path)
    jetson_deployment = load_deployment_config(repo_root / "configs" / "deployments" / "jetson-orin-edge.yaml")
    tensorrt_deployment_report = validate_deployment_runtime_bundle(tensorrt_stack, jetson_deployment)

    reports_root = output_root / "reports"
    _write_json(reports_root / "runtime-benchmark-qualified-holdout.qualification.json", qualification_report.model_dump(mode="json"))
    _write_json(reports_root / "promoted-onnx-runtime.benchmark.json", benchmark_report_dict)
    _write_json(reports_root / "promoted-onnx-runtime.local-dev.validation.json", onnx_deployment_report.model_dump(mode="json"))
    _write_json(
        reports_root / "promoted-tensorrt-runtime.jetson-orin.validation.json",
        tensorrt_deployment_report.model_dump(mode="json"),
    )

    print(f"Fixture root: {output_root}")
    print(f"Promoted ONNX bundle: {onnx_bundle_root}")
    print(f"Promoted TensorRT bundle: {tensorrt_config_path.parent}")
    print(f"Qualification report: {reports_root / 'runtime-benchmark-qualified-holdout.qualification.json'}")
    print(f"Benchmark report: {reports_root / 'promoted-onnx-runtime.benchmark.json'}")
    print(f"Local-dev validation: {reports_root / 'promoted-onnx-runtime.local-dev.validation.json'}")
    print(f"Jetson validation: {reports_root / 'promoted-tensorrt-runtime.jetson-orin.validation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
