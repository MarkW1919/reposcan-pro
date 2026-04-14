from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_profile(example_name: str, output_root: Path, destination: Path) -> Path:
    source = REPO_ROOT / "configs" / "training" / example_name
    profile = yaml.safe_load(source.read_text(encoding="utf-8"))
    profile["output_root"] = output_root.as_posix()
    destination.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    return destination


def _write_rgb_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path, format="JPEG")


def test_detection_training_script_prepares_workspace(tmp_path):
    storage_root = tmp_path / "plate_dataset"
    for split in ("train", "validation", "holdout"):
        (storage_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (storage_root / "labels" / split).mkdir(parents=True, exist_ok=True)
        (storage_root / "images" / split / f"{split}_0001.jpg").write_bytes(b"img")
        (storage_root / "labels" / split / f"{split}_0001.txt").write_text("0 0.5 0.5 0.2 0.1\n", encoding="utf-8")

    manifest_path = tmp_path / "plate-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-plate-yolo",
                "dataset_version: 1",
                "task: plate_detection",
                "format: yolo_detection",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-plate-dataset",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-plate",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:00:00Z",
                "  accepted_tasks: [plate_detection]",
                "splits:",
                "  - split: train",
                "    relative_path: images/train",
                "    label_path: labels/train",
                "  - split: validation",
                "    relative_path: images/validation",
                "    label_path: labels/validation",
                "  - split: holdout",
                "    relative_path: images/holdout",
                "    label_path: labels/holdout",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-detector-finetune.yaml", tmp_path / "runs", tmp_path / "plate-profile.yaml")
    result = _run_script(
        "scripts/train_detection_model.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "plate-detection-smoke",
        "--dry-run",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dataset.yaml" in result.stdout
    assert "yolo" in result.stdout
    assert "mode=export" in result.stdout
    run_manifest = json.loads((tmp_path / "runs" / "plate-detection-smoke" / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["export_command"][0] == "yolo"
    assert any("mode=export" == token for token in run_manifest["export_command"])
    assert any("format=onnx" == token for token in run_manifest["export_command"])


def test_attribute_training_script_prepares_workspace(tmp_path):
    storage_root = tmp_path / "vehicle_color_dataset"
    for split in ("train", "validation"):
        for class_name in ("white", "black"):
            class_dir = storage_root / split / class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            (class_dir / f"{class_name}_0001.jpg").write_bytes(b"img")

    manifest_path = tmp_path / "vehicle-color.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-vehicle-color",
                "dataset_version: 1",
                "task: vehicle_color_classification",
                "format: imagefolder",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-color-dataset",
                "  source_kind: internal_generated",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-color",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:05:00Z",
                "  accepted_tasks: [vehicle_color]",
                "splits:",
                "  - split: train",
                "    relative_path: train",
                "  - split: validation",
                "    relative_path: validation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("vehicle-color-classifier.yaml", tmp_path / "runs", tmp_path / "color-profile.yaml")
    result = _run_script(
        "scripts/train_attribute_classifier.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "vehicle-color-smoke",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "class_index.json" in result.stdout
    assert "Preparation complete. Training was not started." in result.stdout


def test_attribute_training_script_export_only_requires_checkpoint(tmp_path):
    storage_root = tmp_path / "vehicle_color_dataset"
    for split in ("train", "validation"):
        for class_name in ("white", "black"):
            class_dir = storage_root / split / class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            (class_dir / f"{class_name}_0001.jpg").write_bytes(b"img")

    manifest_path = tmp_path / "vehicle-color.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-vehicle-color",
                "dataset_version: 1",
                "task: vehicle_color_classification",
                "format: imagefolder",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-color-dataset",
                "  source_kind: internal_generated",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-color",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:05:00Z",
                "  accepted_tasks: [vehicle_color]",
                "splits:",
                "  - split: train",
                "    relative_path: train",
                "  - split: validation",
                "    relative_path: validation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("vehicle-color-classifier.yaml", tmp_path / "runs", tmp_path / "color-profile.yaml")
    result = _run_script(
        "scripts/train_attribute_classifier.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "vehicle-color-export-only-smoke",
        "--export-only",
    )

    assert result.returncode != 0
    assert "best checkpoint not found for export-only run" in result.stderr


def test_attribute_training_script_includes_initial_checkpoint_in_run_manifest(tmp_path):
    storage_root = tmp_path / "vehicle_color_dataset"
    for split in ("train", "validation"):
        for class_name in ("white", "black"):
            class_dir = storage_root / split / class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            (class_dir / f"{class_name}_0001.jpg").write_bytes(b"img")

    manifest_path = tmp_path / "vehicle-color.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-vehicle-color",
                "dataset_version: 1",
                "task: vehicle_color_classification",
                "format: imagefolder",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-color-dataset",
                "  source_kind: internal_generated",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-color",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:05:00Z",
                "  accepted_tasks: [vehicle_color]",
                "splits:",
                "  - split: train",
                "    relative_path: train",
                "  - split: validation",
                "    relative_path: validation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    checkpoint_path = tmp_path / "warmstart.pt"
    checkpoint_path.write_bytes(b"checkpoint")
    profile_path = _write_profile("vehicle-color-classifier.yaml", tmp_path / "runs", tmp_path / "color-profile.yaml")
    result = _run_script(
        "scripts/train_attribute_classifier.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--initial-checkpoint",
        str(checkpoint_path),
        "--run-name",
        "vehicle-color-warmstart-smoke",
        "--dry-run",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    run_manifest = json.loads((tmp_path / "runs" / "vehicle-color-warmstart-smoke" / "run_manifest.json").read_text(encoding="utf-8"))
    assert "--initial-checkpoint" in run_manifest["training_command"]
    assert str(checkpoint_path) in run_manifest["training_command"]


def test_attribute_training_script_resume_last_uses_existing_checkpoint(tmp_path):
    storage_root = tmp_path / "vehicle_color_dataset"
    for split in ("train", "validation"):
        for class_name in ("white", "black"):
            class_dir = storage_root / split / class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            (class_dir / f"{class_name}_0001.jpg").write_bytes(b"img")

    manifest_path = tmp_path / "vehicle-color.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-vehicle-color",
                "dataset_version: 1",
                "task: vehicle_color_classification",
                "format: imagefolder",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-color-dataset",
                "  source_kind: internal_generated",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-color",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:05:00Z",
                "  accepted_tasks: [vehicle_color]",
                "splits:",
                "  - split: train",
                "    relative_path: train",
                "  - split: validation",
                "    relative_path: validation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("vehicle-color-classifier.yaml", tmp_path / "runs", tmp_path / "color-profile.yaml")
    workspace_dir = tmp_path / "runs" / "vehicle-color-resume-smoke"
    checkpoints_dir = workspace_dir / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    (checkpoints_dir / "last.pt").write_bytes(b"checkpoint")
    (workspace_dir / "training_status.json").write_text(
        json.dumps(
            {
                "run_name": "vehicle-color-resume-smoke",
                "state": "running",
                "current_epoch": 3,
                "total_epochs": 20,
                "best_validation_accuracy": 0.75,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = _run_script(
        "scripts/train_attribute_classifier.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "vehicle-color-resume-smoke",
        "--resume-last",
        "--dry-run",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    run_manifest = json.loads((workspace_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert "--resume-last" in run_manifest["training_command"]
    assert "--initial-checkpoint" not in run_manifest["training_command"]


def test_attribute_training_script_execute_writes_holdout_evaluation_summary(tmp_path):
    storage_root = tmp_path / "vehicle_color_dataset"
    split_colors = {
        "train": {
            "black": [(10, 10, 10), (20, 20, 20), (30, 30, 30)],
            "white": [(225, 225, 225), (235, 235, 235), (245, 245, 245)],
        },
        "validation": {
            "black": [(15, 15, 15)],
            "white": [(240, 240, 240)],
        },
        "holdout": {
            "black": [(25, 25, 25)],
            "white": [(230, 230, 230)],
        },
    }
    for split_name, classes in split_colors.items():
        for class_name, colors in classes.items():
            for index, color in enumerate(colors, start=1):
                _write_rgb_image(
                    storage_root / split_name / class_name / f"{class_name}_{index:04d}.jpg",
                    color,
                )

    manifest_path = tmp_path / "vehicle-color.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-vehicle-color",
                "dataset_version: 1",
                "task: vehicle_color_classification",
                "format: imagefolder",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-color-dataset",
                "  source_kind: internal_generated",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-color",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:05:00Z",
                "  accepted_tasks: [vehicle_color]",
                "splits:",
                "  - split: train",
                "    relative_path: train",
                "  - split: validation",
                "    relative_path: validation",
                "  - split: holdout",
                "    relative_path: holdout",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("vehicle-color-classifier.yaml", tmp_path / "runs", tmp_path / "color-profile.yaml")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["image_size"] = 64
    profile["epochs"] = 1
    profile["batch_size"] = 2
    profile["workers"] = 0
    profile["patience"] = 1
    profile["device"] = "cpu"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    result = _run_script(
        "scripts/train_attribute_classifier.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "vehicle-color-execute-smoke",
        "--execute",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    workspace_dir = tmp_path / "runs" / "vehicle-color-execute-smoke"
    status = json.loads((workspace_dir / "training_status.json").read_text(encoding="utf-8"))
    evaluation_summary = json.loads((workspace_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
    events = (workspace_dir / "training_events.log").read_text(encoding="utf-8")

    assert status["state"] == "completed"
    assert status["holdout_accuracy"] is not None
    assert 0.0 <= status["holdout_accuracy"] <= 1.0
    assert evaluation_summary["validation_strategy"] == "manifest_validation_or_train_internal_split"
    assert evaluation_summary["holdout_split_path"].endswith("holdout")
    assert evaluation_summary["holdout_accuracy"] == status["holdout_accuracy"]
    assert "holdout_evaluated" in events


def test_attribute_training_console_epoch_start_includes_previous_epoch_summary():
    module = _load_script_module(
        "train_attribute_classifier_script",
        REPO_ROOT / "scripts" / "train_attribute_classifier.py",
    )

    message = module._format_epoch_start_message(
        9,
        16,
        {
            "epoch": 8,
            "train_acc": 0.99236,
            "val_acc": 0.84521,
            "best_val": 0.84521,
            "lr": 1.01e-4,
        },
    )

    assert "starting_epoch=9/16" in message
    assert "prev_epoch=8" in message
    assert "train_acc=0.9924" in message
    assert "val_acc=0.8452" in message
    assert "best_val=0.8452" in message
    assert "lr=1.01e-04" in message


def test_attribute_training_console_progress_reports_batch_position():
    module = _load_script_module(
        "train_attribute_classifier_script",
        REPO_ROOT / "scripts" / "train_attribute_classifier.py",
    )

    message = module._format_epoch_progress_message(5, 16, 3, 12, 0.98123)

    assert message == "epoch_progress epoch=5/16 batch=3/12 train_acc=0.9812"


def test_attribute_training_checkpoint_key_remap_supports_dropout_head():
    module = _load_script_module(
        "train_attribute_classifier_script",
        REPO_ROOT / "scripts" / "train_attribute_classifier.py",
    )

    state_dict = {
        "features.0.weight": object(),
        "classifier.1.weight": object(),
        "classifier.1.bias": object(),
    }

    remapped = module._remap_classifier_head_state_dict(
        state_dict,
        head_path="classifier.1",
        target_keys={"features.0.weight", "classifier.1.1.weight", "classifier.1.1.bias"},
    )

    assert "classifier.1.weight" not in remapped
    assert "classifier.1.bias" not in remapped
    assert "classifier.1.1.weight" in remapped
    assert "classifier.1.1.bias" in remapped


def test_attribute_training_resume_cosine_scheduler_matches_uninterrupted_schedule():
    module = _load_script_module(
        "train_attribute_classifier_script",
        REPO_ROOT / "scripts" / "train_attribute_classifier.py",
    )

    import torch

    total_epochs = 16
    completed_epochs = 9
    base_lr = 2e-4

    parameter = torch.nn.Parameter(torch.tensor(1.0))
    optimizer = torch.optim.AdamW([parameter], lr=base_lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_epochs, eta_min=1e-6)
    uninterrupted_lrs: list[float] = []
    for _ in range(total_epochs):
        uninterrupted_lrs.append(optimizer.param_groups[0]["lr"])
        optimizer.step()
        scheduler.step()

    resumed_parameter = torch.nn.Parameter(torch.tensor(1.0))
    resumed_optimizer = torch.optim.AdamW([resumed_parameter], lr=base_lr)
    resumed_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        resumed_optimizer,
        T_max=total_epochs,
        eta_min=1e-6,
    )
    module._resume_cosine_scheduler(resumed_scheduler, completed_epochs=completed_epochs)

    assert resumed_optimizer.param_groups[0]["lr"] == pytest.approx(uninterrupted_lrs[completed_epochs], rel=1e-9)


def test_launch_training_run_streams_attached_output(tmp_path):
    output_path = tmp_path / "foreground-result.txt"
    worker_script = tmp_path / "foreground_worker.py"
    worker_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "print('epoch=1 train_acc=0.9000 val_acc=0.8000', flush=True)",
                "print('stderr: checkpoint pending', file=sys.stderr, flush=True)",
                "Path(sys.argv[1]).write_text('done', encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_name": "foreground-launch-smoke",
                "training_command": [sys.executable, str(worker_script), str(output_path)],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    stdout_log = tmp_path / "stdout.log"
    stderr_log = tmp_path / "stderr.log"
    pid_file = tmp_path / "run.pid"
    result = _run_script(
        "scripts/launch_training_run.py",
        "--run-manifest",
        str(manifest_path),
        "--stdout-log",
        str(stdout_log),
        "--stderr-log",
        str(stderr_log),
        "--pid-file",
        str(pid_file),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Mode: attached" in result.stdout
    assert "epoch=1 train_acc=0.9000 val_acc=0.8000" in result.stdout
    assert "stderr: checkpoint pending" in result.stderr
    assert output_path.read_text(encoding="utf-8") == "done"
    assert "epoch=1 train_acc=0.9000 val_acc=0.8000" in stdout_log.read_text(encoding="utf-8")
    assert "stderr: checkpoint pending" in stderr_log.read_text(encoding="utf-8")
    assert pid_file.exists()


def test_launch_training_run_starts_background_process_from_manifest(tmp_path):
    output_path = tmp_path / "background-result.txt"
    worker_script = tmp_path / "background_worker.py"
    worker_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "import time",
                "time.sleep(1.0)",
                "Path(sys.argv[1]).write_text('done', encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_name": "background-launch-smoke",
                "training_command": [sys.executable, str(worker_script), str(output_path)],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    stdout_log = tmp_path / "stdout.log"
    stderr_log = tmp_path / "stderr.log"
    pid_file = tmp_path / "run.pid"
    result = _run_script(
        "scripts/launch_training_run.py",
        "--run-manifest",
        str(manifest_path),
        "--detached",
        "--stdout-log",
        str(stdout_log),
        "--stderr-log",
        str(stderr_log),
        "--pid-file",
        str(pid_file),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert pid_file.exists()

    for _ in range(30):
        if output_path.exists():
            break
        time.sleep(0.2)

    assert output_path.read_text(encoding="utf-8") == "done"


def test_launch_training_run_marks_stale_running_status_interrupted_on_abnormal_exit(tmp_path):
    workspace_dir = tmp_path / "run_workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "training_status.json").write_text(
        json.dumps(
            {
                "run_name": "abnormal-launch-smoke",
                "state": "running",
                "current_epoch": 7,
                "total_epochs": 40,
                "error_message": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    worker_script = tmp_path / "abnormal_worker.py"
    worker_script.write_text(
        "\n".join(
            [
                "import sys",
                "print('epoch_progress epoch=8/40 batch=31/217 train_acc=0.4400', flush=True)",
                "print('stderr: console closed', file=sys.stderr, flush=True)",
                "sys.exit(7)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path = workspace_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_name": "abnormal-launch-smoke",
                "workspace_dir": str(workspace_dir),
                "training_command": [sys.executable, str(worker_script)],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    stdout_log = tmp_path / "stdout.log"
    stderr_log = tmp_path / "stderr.log"
    pid_file = tmp_path / "run.pid"
    result = _run_script(
        "scripts/launch_training_run.py",
        "--run-manifest",
        str(manifest_path),
        "--stdout-log",
        str(stdout_log),
        "--stderr-log",
        str(stderr_log),
        "--pid-file",
        str(pid_file),
    )

    assert result.returncode == 7, result.stdout + result.stderr
    status = json.loads((workspace_dir / "training_status.json").read_text(encoding="utf-8"))
    events = (workspace_dir / "training_events.log").read_text(encoding="utf-8")
    assert status["state"] == "interrupted"
    assert "code 7" in status["error_message"]
    assert "stderr: console closed" in status["error_message"]
    assert "run_interrupted exit_code=7" in events


def test_launch_training_run_reconciles_stale_running_status_before_relaunch(tmp_path):
    workspace_dir = tmp_path / "run_workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "training_status.json").write_text(
        json.dumps(
            {
                "run_name": "stale-relaunch-smoke",
                "state": "running",
                "current_epoch": 6,
                "total_epochs": 40,
                "best_validation_accuracy": 0.3964,
                "error_message": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    worker_output = tmp_path / "relaunch-result.txt"
    worker_script = tmp_path / "relaunch_worker.py"
    worker_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "print('epoch_started epoch=7/40', flush=True)",
                "Path(sys.argv[1]).write_text('done', encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path = workspace_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_name": "stale-relaunch-smoke",
                "workspace_dir": str(workspace_dir),
                "training_command": [sys.executable, str(worker_script), str(worker_output)],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    stdout_log = tmp_path / "stdout.log"
    stderr_log = tmp_path / "stderr.log"
    pid_file = tmp_path / "run.pid"
    pid_file.write_text("999999", encoding="utf-8")
    stderr_log.write_text("forrtl: error (200): program aborting due to window-CLOSE event\n", encoding="utf-8")

    result = _run_script(
        "scripts/launch_training_run.py",
        "--run-manifest",
        str(manifest_path),
        "--stdout-log",
        str(stdout_log),
        "--stderr-log",
        str(stderr_log),
        "--pid-file",
        str(pid_file),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert worker_output.read_text(encoding="utf-8") == "done"
    status = json.loads((workspace_dir / "training_status.json").read_text(encoding="utf-8"))
    events = (workspace_dir / "training_events.log").read_text(encoding="utf-8")
    assert status["state"] == "interrupted"
    assert "stale running state before launch" in status["error_message"]
    assert "window-CLOSE event" in status["error_message"]
    assert "run_interrupted reason=stale_running_state_before_launch" in events


def test_ocr_training_script_prepares_workspace(tmp_path):
    storage_root = tmp_path / "ocr_dataset"
    for split in ("train", "validation", "holdout"):
        image_root = storage_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (storage_root / split / "labels.csv").write_text(
            "image_file,plate_text\nimages/{split}_0001.png,ABC123\n".replace("{split}", split),
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--run-name",
        "ocr-smoke",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "us_plate_dict.txt" in result.stdout
    assert "Preparation complete. Training was not started." in result.stdout


def test_ocr_training_script_prefers_ppocrv5_when_available(tmp_path):
    storage_root = tmp_path / "ocr_dataset"
    for split in ("train", "validation", "holdout"):
        image_root = storage_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (storage_root / split / "labels.csv").write_text(
            "image_file,plate_text\nimages/{split}_0001.png,ABC123\n".replace("{split}", split),
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    paddle_root = tmp_path / "PaddleOCR"
    (paddle_root / "configs" / "rec" / "PP-OCRv5").mkdir(parents=True, exist_ok=True)
    (paddle_root / "configs" / "rec" / "PP-OCRv5" / "en_PP-OCRv5_rec.yml").write_text("Global:\n", encoding="utf-8")

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--paddleocr-root",
        str(paddle_root),
        "--run-name",
        "ocr-ppocrv5-smoke",
        "--dry-run",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    run_manifest = json.loads((tmp_path / "runs" / "ocr-ppocrv5-smoke" / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["training_command"][2].endswith("scripts\\train_ocr_recognizer.py")
    assert "--execute" in run_manifest["training_command"]
    assert run_manifest["export_command"][1] == str((paddle_root / "tools" / "export_model.py").resolve())
    assert any("en_PP-OCRv5_rec.yml" in token for token in run_manifest["export_command"])


def test_ocr_training_script_detects_ppocrv4_mobile_config(tmp_path):
    storage_root = tmp_path / "ocr_dataset"
    for split in ("train", "validation", "holdout"):
        image_root = storage_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (storage_root / split / "labels.csv").write_text(
            "image_file,plate_text\nimages/{split}_0001.png,ABC123\n".replace("{split}", split),
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    paddle_root = tmp_path / "PaddleOCR"
    (paddle_root / "configs" / "rec" / "PP-OCRv4").mkdir(parents=True, exist_ok=True)
    (paddle_root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_mobile_rec.yml").write_text("Global:\n", encoding="utf-8")

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--paddleocr-root",
        str(paddle_root),
        "--run-name",
        "ocr-ppocrv4-mobile-smoke",
        "--dry-run",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    run_manifest = json.loads((tmp_path / "runs" / "ocr-ppocrv4-mobile-smoke" / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["training_command"][2].endswith("scripts\\train_ocr_recognizer.py")
    assert "--execute" in run_manifest["training_command"]
    assert run_manifest["export_command"][1] == str((paddle_root / "tools" / "export_model.py").resolve())
    assert any("en_PP-OCRv4_mobile_rec.yml" in token for token in run_manifest["export_command"])


def test_ocr_training_script_execute_writes_status_and_exports(tmp_path):
    storage_root = tmp_path / "ocr_dataset"
    for split in ("train", "validation", "holdout"):
        image_root = storage_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (storage_root / split / "labels.csv").write_text(
            "image_file,plate_text\nimages/{split}_0001.png,ABC123\n".replace("{split}", split),
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-23T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    paddle_root = tmp_path / "PaddleOCR"
    (paddle_root / "configs" / "rec" / "PP-OCRv4").mkdir(parents=True, exist_ok=True)
    (paddle_root / "tools").mkdir(parents=True, exist_ok=True)
    (paddle_root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_mobile_rec.yml").write_text("Global:\n", encoding="utf-8")
    (paddle_root / "tools" / "train.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "",
                "save_model_dir = None",
                "for token in sys.argv:",
                "    if token.startswith('Global.save_model_dir='):",
                "        save_model_dir = Path(token.partition('=')[2])",
                "if save_model_dir is None:",
                "    raise SystemExit(2)",
                "save_model_dir.mkdir(parents=True, exist_ok=True)",
                "(save_model_dir / 'best_accuracy.pdparams').write_text('weights', encoding='utf-8')",
                "print('fake train complete')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (paddle_root / "tools" / "export_model.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "",
                "save_inference_dir = None",
                "for token in sys.argv:",
                "    if token.startswith('Global.save_inference_dir='):",
                "        save_inference_dir = Path(token.partition('=')[2])",
                "if save_inference_dir is None:",
                "    raise SystemExit(3)",
                "save_inference_dir.mkdir(parents=True, exist_ok=True)",
                "(save_inference_dir / 'inference.txt').write_text('ok', encoding='utf-8')",
                "print('fake export complete')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--paddleocr-root",
        str(paddle_root),
        "--run-name",
        "ocr-execute-smoke",
        "--execute",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    workspace_dir = tmp_path / "runs" / "ocr-execute-smoke"
    status = json.loads((workspace_dir / "training_status.json").read_text(encoding="utf-8"))
    events = (workspace_dir / "training_events.log").read_text(encoding="utf-8")
    run_manifest = json.loads((workspace_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert status["state"] == "completed"
    assert status["current_epoch"] == 80
    assert Path(status["exported_inference_dir"]).exists()
    assert "run_started" in events
    assert "run_completed" in events
    assert run_manifest["training_command"][2].endswith("scripts\\train_ocr_recognizer.py")
    assert "--execute" in run_manifest["training_command"]
    assert run_manifest["export_command"][1] == str((paddle_root / "tools" / "export_model.py").resolve())


def test_ocr_training_script_mixes_synthetic_support_dataset(tmp_path):
    primary_root = tmp_path / "primary_ocr_dataset"
    support_root = tmp_path / "support_ocr_dataset"

    for index in range(10):
        image_root = primary_root / "train" / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"train_{index:04d}.png").write_bytes(b"img")
    for split in ("validation", "holdout"):
        image_root = primary_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        for index in range(2):
            (image_root / f"{split}_{index:04d}.png").write_bytes(b"img")

    (primary_root / "train" / "labels.csv").write_text(
        "image_file,plate_text\n" + "\n".join(f"train_{index:04d}.png,ABC12{index}" for index in range(10)) + "\n",
        encoding="utf-8",
    )
    (primary_root / "validation" / "labels.csv").write_text(
        "image_file,plate_text\nvalidation_0000.png,VAL001\nvalidation_0001.png,VAL002\n",
        encoding="utf-8",
    )
    (primary_root / "holdout" / "labels.csv").write_text(
        "image_file,plate_text\nholdout_0000.png,HLD001\nholdout_0001.png,HLD002\n",
        encoding="utf-8",
    )

    for index in range(8):
        image_root = support_root / "train" / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"support_{index:04d}.png").write_bytes(b"img")
    for split in ("validation", "holdout"):
        image_root = support_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_support_0000.png").write_bytes(b"img")

    (support_root / "train" / "labels.csv").write_text(
        "image_file,plate_text\n" + "\n".join(f"support_{index:04d}.png,SUP12{index}" for index in range(8)) + "\n",
        encoding="utf-8",
    )
    (support_root / "validation" / "labels.csv").write_text(
        "image_file,plate_text\nvalidation_support_0000.png,SUPVAL1\n",
        encoding="utf-8",
    )
    (support_root / "holdout" / "labels.csv").write_text(
        "image_file,plate_text\nholdout_support_0000.png,SUPHLD1\n",
        encoding="utf-8",
    )

    primary_manifest = tmp_path / "primary-ocr.yaml"
    primary_manifest.write_text(
        "\n".join(
            [
                "dataset_name: tmp-primary-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {primary_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-primary-ocr-dataset",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-primary-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-24T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    support_manifest = tmp_path / "support-ocr.yaml"
    support_manifest.write_text(
        "\n".join(
            [
                "dataset_name: tmp-support-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {support_root.as_posix()}",
                "review_status: pending",
                "provenance:",
                "  source_name: tmp-support-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-support-ocr",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(primary_manifest),
        "--support-dataset-manifest",
        str(support_manifest),
        "--run-name",
        "ocr-support-smoke",
        "--allow-pending",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    workspace_dir = tmp_path / "runs" / "ocr-support-smoke"
    train_list = (workspace_dir / "train_list.txt").read_text(encoding="utf-8").strip().splitlines()
    validation_list = (workspace_dir / "validation_list.txt").read_text(encoding="utf-8").strip().splitlines()
    support_summary = json.loads((workspace_dir / "ocr_support_mix_summary.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((workspace_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert len(train_list) == 12
    assert len(validation_list) == 2
    assert any(line.startswith(support_root.as_posix()) for line in train_list if "SUP" in line)
    assert support_summary["selected_support_train_rows"] == 2
    assert support_summary["max_support_train_rows"] == 2
    assert support_summary["support_datasets"][0]["selected_train_rows"] == 2
    assert run_manifest["auxiliary_dataset_manifest_paths"] == [str(support_manifest)]


def test_ocr_support_manifest_requires_positive_ratio(tmp_path):
    dataset_root = tmp_path / "ocr_dataset"
    support_root = tmp_path / "support_ocr_dataset"

    for split in ("train", "validation"):
        image_root = dataset_root / split / "images"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / f"{split}_0001.png").write_bytes(b"img")
        (dataset_root / split / "labels.csv").write_text(
            f"image_file,plate_text\n{split}_0001.png,ABC123\n",
            encoding="utf-8",
        )
    (dataset_root / "holdout" / "images").mkdir(parents=True, exist_ok=True)
    (dataset_root / "holdout" / "images" / "holdout_0001.png").write_bytes(b"img")
    (dataset_root / "holdout" / "labels.csv").write_text("image_file,plate_text\nholdout_0001.png,ABC123\n", encoding="utf-8")

    (support_root / "train" / "images").mkdir(parents=True, exist_ok=True)
    (support_root / "train" / "images" / "support_0001.png").write_bytes(b"img")
    (support_root / "train" / "labels.csv").write_text("image_file,plate_text\nsupport_0001.png,SUP123\n", encoding="utf-8")
    for split in ("validation", "holdout"):
        (support_root / split / "images").mkdir(parents=True, exist_ok=True)
        (support_root / split / "images" / f"{split}_support_0001.png").write_bytes(b"img")
        (support_root / split / "labels.csv").write_text(
            f"image_file,plate_text\n{split}_support_0001.png,SUP123\n",
            encoding="utf-8",
        )

    manifest_path = tmp_path / "ocr-dataset.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "dataset_name: tmp-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {dataset_root.as_posix()}",
                "review_status: approved",
                "provenance:",
                "  source_name: tmp-ocr-dataset",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-ocr",
                "annotation_review:",
                "  reviewer: qa_01",
                "  reviewed_at_utc: 2026-03-24T08:10:00Z",
                "  accepted_tasks: [plate_ocr]",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    support_manifest = tmp_path / "support-ocr.yaml"
    support_manifest.write_text(
        "\n".join(
            [
                "dataset_name: tmp-support-ocr",
                "dataset_version: 1",
                "task: plate_ocr",
                "format: ocr_manifest",
                f"storage_root: {support_root.as_posix()}",
                "review_status: pending",
                "provenance:",
                "  source_name: tmp-support-ocr-dataset",
                "  source_kind: synthetic",
                "  license_tier: internal",
                "  license_name: internal",
                "  license_reference: internal://tmp-support-ocr",
                "splits:",
                "  - split: train",
                "    relative_path: train/images",
                "    label_path: train/labels.csv",
                "  - split: validation",
                "    relative_path: validation/images",
                "    label_path: validation/labels.csv",
                "  - split: holdout",
                "    relative_path: holdout/images",
                "    label_path: holdout/labels.csv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile_path = _write_profile("plate-ocr-finetune.yaml", tmp_path / "runs", tmp_path / "ocr-profile.yaml")
    profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile_data["augmentation"]["synthetic_support_ratio"] = 0.0
    profile_path.write_text(yaml.safe_dump(profile_data, sort_keys=False), encoding="utf-8")

    result = _run_script(
        "scripts/train_ocr_recognizer.py",
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(manifest_path),
        "--support-dataset-manifest",
        str(support_manifest),
        "--run-name",
        "ocr-support-zero-ratio",
        "--allow-pending",
    )

    assert result.returncode == 1
    assert "synthetic_support_ratio is 0.0" in result.stderr
