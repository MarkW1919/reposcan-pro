from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
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
    parser.add_argument("--support-dataset-manifest", action="append", default=[])
    parser.add_argument("--paddleocr-root")
    parser.add_argument("--run-name")
    parser.add_argument("--resume-checkpoint")
    parser.add_argument("--allow-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _utc_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_training_status(
    path: Path,
    *,
    state: str,
    run_name: str,
    total_epochs: int,
    current_epoch: int = 0,
    best_checkpoint: Path | None = None,
    exported_inference_dir: Path | None = None,
    error_message: str | None = None,
) -> None:
    payload = {
        "run_name": run_name,
        "state": state,
        "updated_at_utc": _utc_now_utc(),
        "current_epoch": current_epoch,
        "total_epochs": total_epochs,
        "best_checkpoint": str(best_checkpoint) if best_checkpoint is not None else None,
        "exported_inference_dir": str(exported_inference_dir) if exported_inference_dir is not None else None,
        "error_message": error_message,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_training_event(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_utc_now_utc()} {message}\n")


def _find_paddle_config(root: Path) -> Path:
    candidates = [
        root / "configs" / "rec" / "PP-OCRv5" / "en_PP-OCRv5_rec.yml",
        root / "configs" / "rec" / "PP-OCRv5" / "en_PP-OCRv5_mobile_rec.yml",
        root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_rec.yml",
        root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_mobile_rec.yml",
        root / "configs" / "rec" / "PP-OCRv3" / "en_PP-OCRv3_rec.yml",
        root / "configs" / "rec" / "PP-OCRv3" / "en_PP-OCRv3_mobile_rec.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"could not find a PaddleOCR English recognition config under {root}")


def _resolve_base_model_path(base_model: str | None, paddle_root: Path) -> Path | None:
    if not base_model:
        return None
    model_path = Path(base_model)
    if model_path.is_absolute():
        return model_path.resolve()
    return (paddle_root / model_path).resolve()


def _should_use_gpu(profile) -> bool:
    device = profile.device.strip().lower()
    if device in {"gpu", "cuda"}:
        return True
    if device == "cpu":
        return False
    if device != "auto":
        return False
    try:
        import paddle
    except Exception:
        return False
    try:
        return bool(paddle.is_compiled_with_cuda())
    except Exception:
        return False


def _loader_workers(profile) -> int:
    return 0 if sys.platform == "win32" else profile.workers


def _estimate_eval_interval(train_list: str, batch_size: int) -> int:
    train_rows = 0
    with Path(train_list).open("r", encoding="utf-8") as handle:
        for _ in handle:
            train_rows += 1
    estimated_steps = math.ceil(train_rows / max(batch_size, 1)) if train_rows else 1
    return min(2000, max(10, estimated_steps))


def _count_label_rows(label_file: str) -> int:
    with Path(label_file).open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _estimate_eval_batch_size(validation_list: str, batch_size: int) -> int:
    validation_rows = _count_label_rows(validation_list)
    if validation_rows <= 0:
        return batch_size
    if sys.platform != "win32":
        return batch_size
    if validation_rows > batch_size:
        return batch_size
    # PaddleOCR skips len(dataloader) - 1 batches on Windows. Keep at least two
    # validation batches so a small validation split is actually evaluated.
    return max(1, validation_rows // 2)


def _build_train_command(
    *,
    paddle_root: Path,
    config_path: Path,
    workspace_dir: Path,
    storage_root: str,
    train_list: str,
    validation_list: str,
    char_dict: str,
    base_model: Path | None,
    resume_checkpoint: Path | None,
    profile,
) -> list[str]:
    use_gpu = _should_use_gpu(profile)
    workers = _loader_workers(profile)
    eval_interval = _estimate_eval_interval(train_list, profile.batch_size)
    eval_batch_size = _estimate_eval_batch_size(validation_list, profile.batch_size)
    command = [
        str(Path(sys.executable).resolve()),
        str((paddle_root / "tools" / "train.py").resolve()),
        "-c",
        str(config_path.resolve()),
        "-o",
        f"Global.save_model_dir={(workspace_dir / 'output').as_posix()}",
        f"Global.character_dict_path={Path(char_dict).as_posix()}",
        "Global.use_space_char=False",
        f"Train.dataset.data_dir={Path(storage_root).as_posix()}",
        f"Train.dataset.label_file_list=[\"{Path(train_list).as_posix()}\"]",
        f"Eval.dataset.data_dir={Path(storage_root).as_posix()}",
        f"Eval.dataset.label_file_list=[\"{Path(validation_list).as_posix()}\"]",
        f"Global.use_gpu={'True' if use_gpu else 'False'}",
        "Global.distributed=False",
        f"Global.epoch_num={profile.epochs}",
        "Global.print_batch_step=1",
        "Global.save_epoch_step=1",
        f"Global.eval_batch_step=[0,{eval_interval}]",
        f"Train.loader.batch_size_per_card={profile.batch_size}",
        f"Eval.loader.batch_size_per_card={eval_batch_size}",
        f"Train.loader.num_workers={workers}",
        f"Eval.loader.num_workers={workers}",
    ]
    if resume_checkpoint is not None:
        command.append(f"Global.checkpoints={resume_checkpoint.as_posix()}")
    elif base_model is not None:
        command.append(f"Global.pretrained_model={base_model.as_posix()}")
    return command


def _build_export_command(
    *,
    paddle_root: Path,
    config_path: Path,
    workspace_dir: Path,
    char_dict: str,
    profile,
) -> list[str]:
    use_gpu = _should_use_gpu(profile)
    return [
        str(Path(sys.executable).resolve()),
        str((paddle_root / "tools" / "export_model.py").resolve()),
        "-c",
        str(config_path.resolve()),
        "-o",
        f"Global.pretrained_model={(workspace_dir / 'output' / 'best_accuracy').as_posix()}",
        f"Global.save_inference_dir={(workspace_dir / 'inference_export').as_posix()}",
        f"Global.character_dict_path={Path(char_dict).as_posix()}",
        "Global.use_space_char=False",
        f"Global.use_gpu={'True' if use_gpu else 'False'}",
        "Global.distributed=False",
    ]


def _build_wrapper_training_command(
    *,
    profile_path: Path,
    dataset_manifest_path: Path,
    support_manifest_paths: list[Path],
    paddle_root: Path,
    run_name: str,
    allow_pending: bool,
    resume_checkpoint: Path | None,
) -> list[str]:
    command = [
        str(Path(sys.executable).resolve()),
        "-u",
        str(Path(__file__).resolve()),
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(dataset_manifest_path),
        "--paddleocr-root",
        str(paddle_root),
        "--run-name",
        run_name,
        "--execute",
    ]
    for support_manifest_path in support_manifest_paths:
        command.extend(["--support-dataset-manifest", str(support_manifest_path)])
    if allow_pending:
        command.append("--allow-pending")
    if resume_checkpoint is not None:
        command.extend(["--resume-checkpoint", str(resume_checkpoint)])
    return command


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
    support_manifest_paths = [
        (repo_root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        for raw_path in args.support_dataset_manifest
    ]
    resume_checkpoint = (
        (repo_root / args.resume_checkpoint).resolve()
        if args.resume_checkpoint and not Path(args.resume_checkpoint).is_absolute()
        else Path(args.resume_checkpoint).resolve()
        if args.resume_checkpoint
        else None
    )

    profile = load_training_profile(profile_path)
    dataset_manifest = load_training_dataset_manifest(dataset_manifest_path)
    ensure_dataset_review_status(dataset_manifest, allow_pending=profile.allow_pending_review or args.allow_pending)
    support_manifests = []
    for support_manifest_path in support_manifest_paths:
        support_manifest = load_training_dataset_manifest(support_manifest_path)
        ensure_dataset_review_status(support_manifest, allow_pending=profile.allow_pending_review or args.allow_pending)
        support_manifests.append(support_manifest)

    run_name = make_run_name(profile.profile_name, args.run_name)
    output_root = Path(profile.output_root)
    if not output_root.is_absolute():
        output_root = (repo_root / output_root).resolve()
    workspace_dir = output_root / run_name
    workspace_dir.mkdir(parents=True, exist_ok=True)
    status_path = workspace_dir / "training_status.json"
    events_path = workspace_dir / "training_events.log"
    best_checkpoint = workspace_dir / "output" / "best_accuracy"
    inference_export_dir = workspace_dir / "inference_export"

    prepared_files, notes, context = prepare_ocr_workspace(
        repo_root,
        profile,
        dataset_manifest,
        workspace_dir,
        support_manifests=support_manifests,
        support_manifest_paths=support_manifest_paths,
    )
    training_command: list[str] = []
    export_command: list[str] = []
    direct_train_command: list[str] = []
    paddle_root = Path(args.paddleocr_root).resolve() if args.paddleocr_root else None
    if paddle_root is not None:
        config_path = _find_paddle_config(paddle_root)
        base_model_path = _resolve_base_model_path(profile.base_model, paddle_root)
        direct_train_command = _build_train_command(
            paddle_root=paddle_root,
            config_path=config_path,
            workspace_dir=workspace_dir,
            storage_root=context["storage_root"],
            train_list=context["train_list"],
            validation_list=context["validation_list"],
            char_dict=context["char_dict_path"],
            base_model=base_model_path,
            resume_checkpoint=resume_checkpoint,
            profile=profile,
        )
        export_command = _build_export_command(
            paddle_root=paddle_root,
            config_path=config_path,
            workspace_dir=workspace_dir,
            char_dict=context["char_dict_path"],
            profile=profile,
        )
        training_command = _build_wrapper_training_command(
            profile_path=profile_path.resolve(),
            dataset_manifest_path=dataset_manifest_path.resolve(),
            support_manifest_paths=support_manifest_paths,
            paddle_root=paddle_root,
            run_name=run_name,
            allow_pending=profile.allow_pending_review or args.allow_pending,
            resume_checkpoint=resume_checkpoint,
        )
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
        auxiliary_dataset_manifest_paths=[str(path) for path in support_manifest_paths],
    )
    run_manifest_path = workspace_dir / "run_manifest.json"
    run_manifest_path.write_text(run_manifest.model_dump_json(indent=2), encoding="utf-8")

    print(f"Run name: {run_name}")
    print(f"Workspace: {workspace_dir}")
    print(f"Run manifest: {run_manifest_path}")
    for prepared_file in prepared_files:
        print(f"- prepared: {prepared_file}")

    if args.dry_run or not args.execute:
        if direct_train_command:
            print("Train command:")
            print(subprocess.list2cmdline(direct_train_command))
            print("Export command:")
            print(subprocess.list2cmdline(export_command))
        else:
            print("PaddleOCR root not supplied, so only workspace preparation was completed.")
        if not args.execute:
            print("Preparation complete. Training was not started.")
        return 0

    if paddle_root is None:
        raise ValueError("--paddleocr-root is required when --execute is used")

    _write_training_status(
        status_path,
        state="running",
        run_name=run_name,
        total_epochs=profile.epochs,
        current_epoch=0,
        best_checkpoint=best_checkpoint,
    )
    _append_training_event(events_path, f"run_started total_epochs={profile.epochs} workspace={workspace_dir}")

    train_result = subprocess.run(direct_train_command, cwd=repo_root, check=False)
    if train_result.returncode != 0:
        _write_training_status(
            status_path,
            state="failed",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=0,
            best_checkpoint=best_checkpoint if best_checkpoint.with_suffix(".pdparams").exists() else None,
            error_message=f"training command exited with code {train_result.returncode}",
        )
        _append_training_event(events_path, f"run_failed stage=train exit_code={train_result.returncode}")
        return train_result.returncode

    export_result = subprocess.run(export_command, cwd=repo_root, check=False)
    if export_result.returncode != 0:
        _write_training_status(
            status_path,
            state="failed",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=profile.epochs,
            best_checkpoint=best_checkpoint if best_checkpoint.with_suffix(".pdparams").exists() else None,
            error_message=f"export command exited with code {export_result.returncode}",
        )
        _append_training_event(events_path, f"run_failed stage=export exit_code={export_result.returncode}")
        return export_result.returncode

    _write_training_status(
        status_path,
        state="completed",
        run_name=run_name,
        total_epochs=profile.epochs,
        current_epoch=profile.epochs,
        best_checkpoint=best_checkpoint if best_checkpoint.with_suffix(".pdparams").exists() else best_checkpoint,
        exported_inference_dir=inference_export_dir,
    )
    _append_training_event(events_path, f"run_completed exported_inference_dir={inference_export_dir}")
    print(f"Exported OCR inference dir: {inference_export_dir}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
