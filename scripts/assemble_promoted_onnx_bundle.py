from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


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
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble a promoted ONNX bundle from exported per-stage ONNX artifacts.",
    )
    parser.add_argument("--template-model-config", default="configs/models/local-onnx-runtime.yaml")
    parser.add_argument("--vehicle-detector-artifact", required=True)
    parser.add_argument("--plate-detector-artifact", required=True)
    parser.add_argument("--ocr-artifact", required=True)
    parser.add_argument("--classifier-artifact")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bundle-name")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--exported-at-utc")
    parser.add_argument("--source-run-id")
    parser.add_argument("--source-checkpoint-ref")
    parser.add_argument("--dataset-manifest", action="append", default=[])
    parser.add_argument("--export-tool")
    parser.add_argument("--export-tool-version")
    parser.add_argument("--opset-version", type=int)
    parser.add_argument("--precision")
    parser.add_argument("--target-runtime", default="onnxruntime")
    parser.add_argument("--notes")
    return parser.parse_args()


def _resolve_path(repo_root: Path, raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_model_config
    from reposcan_inference import package_exported_onnx_bundle

    args = parse_args()
    template_model_config_path = _resolve_path(repo_root, args.template_model_config)
    template_stack = load_model_config(template_model_config_path)
    output_dir = Path(args.output_dir)

    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    elif output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory '{output_dir}' already exists and is not empty. Use --overwrite to replace it.")

    report = package_exported_onnx_bundle(
        template_stack,
        vehicle_detector_artifact=_resolve_path(repo_root, args.vehicle_detector_artifact),
        plate_detector_artifact=_resolve_path(repo_root, args.plate_detector_artifact),
        ocr_artifact=_resolve_path(repo_root, args.ocr_artifact),
        classifier_artifact=_resolve_path(repo_root, args.classifier_artifact),
        output_dir=output_dir,
        bundle_name=args.bundle_name,
        exported_at_utc=args.exported_at_utc,
        source_run_id=args.source_run_id,
        source_checkpoint_ref=args.source_checkpoint_ref,
        dataset_manifests=args.dataset_manifest,
        export_tool=args.export_tool,
        export_tool_version=args.export_tool_version,
        opset_version=args.opset_version,
        precision=args.precision,
        target_runtime=args.target_runtime,
        notes=args.notes,
    )

    print(f"Bundle: {report.bundle_name}")
    print(f"Output dir: {report.output_dir}")
    print(f"Config path: {report.config_path}")
    print(f"Ready: {'yes' if report.ready else 'no'}")
    for stage in report.validation.stages:
        print(f"- {stage.stage}: ready={'yes' if stage.ready else 'no'}")
        for issue in stage.issues:
            print(f"  - {issue.severity}: {issue.message}")

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
