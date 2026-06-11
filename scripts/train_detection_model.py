from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "ml" / "training" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or run a RepoScan detection-model training workflow.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--run-name")
    parser.add_argument("--allow-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _build_export_command(workspace_dir: Path, profile) -> list[str]:
    return [
        "yolo",
        "task=detect",
        "mode=export",
        f"model={(workspace_dir / 'weights' / 'best.pt')}",
        "format=onnx",
        f"imgsz={profile.image_size}",
        "dynamic=True",
        "simplify=False",
        "opset=17",
        "device=cpu",
    ]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest, load_training_profile
    from reposcan_training import (
        build_run_manifest,
        ensure_dataset_review_status,
        make_run_name,
        prepare_detection_workspace,
    )

    args = parse_args()
    profile_path = repo_root / args.profile if not Path(args.profile).is_absolute() else Path(args.profile)
    dataset_manifest_path = (
        repo_root / args.dataset_manifest if not Path(args.dataset_manifest).is_absolute() else Path(args.dataset_manifest)
    )

    profile = load_training_profile(profile_path)
    dataset_manifest = load_training_dataset_manifest(dataset_manifest_path)
    ensure_dataset_review_status(dataset_manifest, allow_pending=profile.allow_pending_review or args.allow_pending)

    run_name = make_run_name(profile.profile_name, args.run_name)
    output_root = Path(profile.output_root)
    if not output_root.is_absolute():
        output_root = (repo_root / output_root).resolve()
    workspace_dir = output_root / run_name
    workspace_dir.mkdir(parents=True, exist_ok=True)

    prepared_files, notes, context = prepare_detection_workspace(repo_root, profile, dataset_manifest, workspace_dir)
    training_command = [
        "yolo",
        "task=detect",
        "mode=train",
        f"model={profile.base_model or 'yolov8n.pt'}",
        f"data={context['dataset_yaml']}",
        f"epochs={profile.epochs}",
        f"imgsz={profile.image_size}",
        f"batch={profile.batch_size}",
        f"workers={profile.workers}",
        f"patience={profile.patience}",
        f"device={profile.device}",
    ]
    export_command = _build_export_command(workspace_dir, profile)

    run_manifest = build_run_manifest(
        profile=profile,
        manifest=dataset_manifest,
        dataset_manifest_path=dataset_manifest_path,
        workspace_dir=workspace_dir,
        run_name=run_name,
        prepared_files=prepared_files,
        training_command=training_command,
        export_command=export_command,
        notes=notes,
    )
    run_manifest_path = workspace_dir / "run_manifest.json"
    run_manifest_path.write_text(run_manifest.model_dump_json(indent=2), encoding="utf-8")

    print(f"Run name: {run_name}")
    print(f"Workspace: {workspace_dir}")
    print(f"Run manifest: {run_manifest_path}")
    for prepared_file in prepared_files:
        print(f"- prepared: {prepared_file}")

    if args.dry_run or not args.execute:
        print("Training command:")
        print(subprocess.list2cmdline(training_command))
        print("Export command:")
        print(subprocess.list2cmdline(export_command))
        if not args.execute:
            print("Preparation complete. Training was not started.")
        return 0

    try:
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is required to execute detection training") from exc

    resolved_device = profile.device
    if resolved_device == "auto":
        resolved_device = "0" if torch.cuda.is_available() else "cpu"

    model = YOLO(profile.base_model or "yolov8n.pt")
    model.train(
        data=context["dataset_yaml"],
        project=str(workspace_dir.parent),
        name=workspace_dir.name,
        epochs=profile.epochs,
        imgsz=profile.image_size,
        batch=profile.batch_size,
        device=resolved_device,
        workers=profile.workers,
        patience=profile.patience,
        amp=profile.use_amp,
        exist_ok=True,
    )

    save_dir = Path(getattr(model.trainer, "save_dir", workspace_dir))
    best_weights = save_dir / "weights" / "best.pt"
    if not best_weights.exists():
        raise RuntimeError(f"Ultralytics training completed but no best checkpoint was found at {best_weights}")
    model = YOLO(best_weights)
    export_path = model.export(
        format="onnx",
        imgsz=profile.image_size,
        dynamic=True,
        simplify=False,
        opset=17,
        device="cpu",
    )
    print(f"Training run dir: {save_dir}")
    print(f"Exported ONNX: {export_path}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
