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
    parser = argparse.ArgumentParser(description="Prepare or run a RepoScan OCR training workflow.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--paddleocr-root")
    parser.add_argument("--run-name")
    parser.add_argument("--allow-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _find_paddle_config(root: Path) -> Path:
    candidates = [
        root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_rec.yml",
        root / "configs" / "rec" / "PP-OCRv3" / "en_PP-OCRv3_rec.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"could not find a PaddleOCR English recognition config under {root}")


def _build_train_command(config_path: Path, workspace_dir: Path, storage_root: str, train_list: str, validation_list: str, char_dict: str, base_model: str | None) -> list[str]:
    command = [
        str(Path(sys.executable).resolve()),
        "tools/train.py",
        "-c",
        str(config_path),
        "-o",
        f"Global.save_model_dir={(workspace_dir / 'output').as_posix()}",
        f"Global.character_dict_path={Path(char_dict).as_posix()}",
        "Global.use_space_char=False",
        f"Train.dataset.data_dir={Path(storage_root).as_posix()}",
        f"Train.dataset.label_file_list=[\"{Path(train_list).as_posix()}\"]",
        f"Eval.dataset.data_dir={Path(storage_root).as_posix()}",
        f"Eval.dataset.label_file_list=[\"{Path(validation_list).as_posix()}\"]",
    ]
    if base_model:
        command.append(f"Global.pretrained_model={base_model}")
    return command


def _build_export_command(config_path: Path, workspace_dir: Path, char_dict: str) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        "tools/export_model.py",
        "-c",
        str(config_path),
        "-o",
        f"Global.pretrained_model={(workspace_dir / 'output' / 'best_accuracy').as_posix()}",
        f"Global.save_inference_dir={(workspace_dir / 'inference_export').as_posix()}",
        f"Global.character_dict_path={Path(char_dict).as_posix()}",
        "Global.use_space_char=False",
    ]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest, load_training_profile
    from reposcan_training import (
        build_run_manifest,
        ensure_dataset_review_status,
        make_run_name,
        prepare_ocr_workspace,
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

    prepared_files, notes, context = prepare_ocr_workspace(repo_root, profile, dataset_manifest, workspace_dir)
    training_command: list[str] = []
    export_command: list[str] = []
    paddle_root = Path(args.paddleocr_root).resolve() if args.paddleocr_root else None
    if paddle_root is not None:
        config_path = _find_paddle_config(paddle_root)
        training_command = _build_train_command(
            config_path,
            workspace_dir,
            context["storage_root"],
            context["train_list"],
            context["validation_list"],
            context["char_dict_path"],
            profile.base_model,
        )
        export_command = _build_export_command(config_path, workspace_dir, context["char_dict_path"])
    else:
        notes.append("paddleocr_root required for command generation and execution")

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
        if training_command:
            print("Train command:")
            print(subprocess.list2cmdline(training_command))
            print("Export command:")
            print(subprocess.list2cmdline(export_command))
        else:
            print("PaddleOCR root not supplied, so only workspace preparation was completed.")
        if not args.execute:
            print("Preparation complete. Training was not started.")
        return 0

    if paddle_root is None:
        raise ValueError("--paddleocr-root is required when --execute is used")

    train_result = subprocess.run(training_command, cwd=paddle_root, check=False)
    if train_result.returncode != 0:
        return train_result.returncode

    export_result = subprocess.run(export_command, cwd=paddle_root, check=False)
    if export_result.returncode != 0:
        return export_result.returncode

    print(f"Exported OCR inference dir: {workspace_dir / 'inference_export'}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
