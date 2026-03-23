from __future__ import annotations

import argparse
import json
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
    parser = argparse.ArgumentParser(description="Generate a promoted model artifact manifest for one stage.")
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--stage", required=True, choices=["vehicle_detector", "plate_detector", "ocr", "classifier"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--exported-at-utc")
    parser.add_argument("--source-run-id")
    parser.add_argument("--source-checkpoint-ref")
    parser.add_argument("--dataset-manifest", action="append", default=[])
    parser.add_argument("--export-tool")
    parser.add_argument("--export-tool-version")
    parser.add_argument("--opset-version", type=int)
    parser.add_argument("--precision")
    parser.add_argument("--target-runtime")
    parser.add_argument("--notes")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_model_config
    from reposcan_inference.promotion import build_model_artifact_manifest

    args = parse_args()
    model_stack = load_model_config(repo_root / args.model_config)
    stage_config = getattr(model_stack, args.stage)
    if stage_config is None:
        raise ValueError(f"Stage '{args.stage}' is not configured in '{args.model_config}'.")

    manifest = build_model_artifact_manifest(
        stage=args.stage,
        model_config=stage_config,
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

    output_path = repo_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2), encoding="utf-8")
    print(f"Wrote artifact manifest to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
