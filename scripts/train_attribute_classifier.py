from __future__ import annotations

import argparse
import json
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
    parser = argparse.ArgumentParser(description="Prepare or run a RepoScan attribute-classifier training workflow.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--run-name")
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
    train_accuracy: float | None = None,
    validation_accuracy: float | None = None,
    best_validation_accuracy: float | None = None,
    best_checkpoint: Path | None = None,
    exported_onnx: Path | None = None,
    label_metadata: Path | None = None,
    error_message: str | None = None,
) -> None:
    payload = {
        "run_name": run_name,
        "state": state,
        "updated_at_utc": _utc_now_utc(),
        "current_epoch": current_epoch,
        "total_epochs": total_epochs,
        "train_accuracy": train_accuracy,
        "validation_accuracy": validation_accuracy,
        "best_validation_accuracy": best_validation_accuracy,
        "best_checkpoint": str(best_checkpoint) if best_checkpoint is not None else None,
        "exported_onnx": str(exported_onnx) if exported_onnx is not None else None,
        "label_metadata": str(label_metadata) if label_metadata is not None else None,
        "error_message": error_message,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_training_event(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_utc_now_utc()} {message}\n")


def _module_from_path(root, path: str):
    current = root
    for token in path.split("."):
        current = current[int(token)] if token.isdigit() else getattr(current, token)
    return current


def _replace_module(root, path: str, new_module) -> None:
    tokens = path.split(".")
    parent = root
    for token in tokens[:-1]:
        parent = parent[int(token)] if token.isdigit() else getattr(parent, token)
    final_token = tokens[-1]
    if final_token.isdigit():
        parent[int(final_token)] = new_module
    else:
        setattr(parent, final_token, new_module)


def _build_torchvision_model(base_model: str | None, *, num_classes: int):
    import torch
    from torchvision import models

    model_name = (base_model or "resnet18").strip().lower()
    supported_models = {
        "resnet18": ("resnet18", "ResNet18_Weights", "fc"),
        "resnet50": ("resnet50", "ResNet50_Weights", "fc"),
        "efficientnet_b0": ("efficientnet_b0", "EfficientNet_B0_Weights", "classifier.1"),
        "mobilenet_v3_large": ("mobilenet_v3_large", "MobileNet_V3_Large_Weights", "classifier.3"),
        "convnext_tiny": ("convnext_tiny", "ConvNeXt_Tiny_Weights", "classifier.2"),
    }
    if model_name not in supported_models:
        supported = ", ".join(sorted(supported_models))
        raise ValueError(f"Unsupported torchvision base_model '{model_name}'. Supported models: {supported}")

    constructor_name, weights_name, head_path = supported_models[model_name]
    constructor = getattr(models, constructor_name)
    weights_enum = getattr(models, weights_name)
    try:
        model = constructor(weights=weights_enum.DEFAULT)
        print(f"Using torchvision {constructor_name} default pretrained weights.")
    except Exception:
        model = constructor(weights=None)
        print(f"Falling back to randomly initialized {constructor_name} weights.")

    classifier_head = _module_from_path(model, head_path)
    in_features = classifier_head.in_features
    _replace_module(model, head_path, torch.nn.Linear(in_features, num_classes))
    return model


def _evaluate(model, loader, device) -> float:
    import torch

    model.eval()
    total = 0
    correct = 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            logits = model(images)
            preds = torch.argmax(logits, dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)
    return (correct / total) if total else 0.0


def _build_imagefolder_loaders(profile, manifest, repo_root: Path):
    import torch
    from torchvision import datasets, transforms

    from reposcan_contracts.dataset import DatasetSplit
    from reposcan_training import resolve_storage_root

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    split_map = {split.split: split for split in manifest.splits}
    train_root = storage_root / split_map[DatasetSplit.train].relative_path
    validation_split = split_map.get(DatasetSplit.validation)
    validation_root = storage_root / validation_split.relative_path if validation_split else None

    transform = transforms.Compose(
        [
            transforms.Resize((profile.image_size, profile.image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )

    train_dataset = datasets.ImageFolder(str(train_root), transform=transform)
    if validation_root is not None and validation_root.exists():
        validation_dataset = datasets.ImageFolder(str(validation_root), transform=transform)
        class_names = list(train_dataset.classes)
    else:
        if len(train_dataset) < 10:
            raise ValueError("imagefolder training requires at least 10 samples when no validation split is provided")
        val_size = max(1, int(len(train_dataset) * 0.1))
        train_size = len(train_dataset) - val_size
        train_dataset, validation_dataset = torch.utils.data.random_split(
            train_dataset,
            [train_size, val_size],
            generator=torch.Generator().manual_seed(profile.seed),
        )
        class_names = list(train_dataset.dataset.classes)

    # num_workers=0 on Windows to avoid spawn-based multiprocessing errors with
    # DataLoader. On Linux (Jetson) the profile value is used as configured.
    import platform
    num_workers = 0 if platform.system() == "Windows" else profile.workers
    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=profile.batch_size,
        shuffle=True,
        num_workers=num_workers,
    )
    validation_loader = torch.utils.data.DataLoader(
        validation_dataset,
        batch_size=profile.batch_size,
        shuffle=False,
        num_workers=num_workers,
    )
    return train_loader, validation_loader, class_names


def _build_stanford_cars_loaders(profile, manifest, repo_root: Path):
    import torch
    from PIL import Image
    from scipy.io import loadmat
    from torch.utils.data import Dataset, random_split
    from torchvision import transforms

    from reposcan_training import resolve_storage_root

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)

    class StanfordCarsTrainDataset(Dataset):
        def __init__(self, root: Path):
            self.root = root
            self.transform = transforms.Compose(
                [
                    transforms.Resize((profile.image_size, profile.image_size)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ]
            )
            ann_path = self.root / "devkit" / "cars_train_annos.mat"
            if not ann_path.exists():
                ann_path = self.root / "cars_train_annos.mat"
            meta_path = self.root / "devkit" / "cars_meta.mat"
            if not meta_path.exists():
                meta_path = self.root / "cars_meta.mat"
            ann = loadmat(str(ann_path))["annotations"][0]
            meta = loadmat(str(meta_path))["class_names"][0]
            self.classes = [str(item[0]) for item in meta]
            self.samples = []
            train_dir = self.root / "cars_train"
            for item in ann:
                class_index = int(item["class"][0, 0]) - 1
                filename = str(item["fname"][0])
                image_path = train_dir / filename
                if image_path.exists():
                    self.samples.append((image_path, class_index))

        def __len__(self):
            return len(self.samples)

        def __getitem__(self, index):
            image_path, target = self.samples[index]
            image = Image.open(image_path).convert("RGB")
            return self.transform(image), target

    dataset = StanfordCarsTrainDataset(storage_root)
    val_size = max(1, int(len(dataset) * 0.1))
    train_size = len(dataset) - val_size
    train_dataset, validation_dataset = random_split(
        dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(profile.seed),
    )
    import platform
    num_workers = 0 if platform.system() == "Windows" else profile.workers
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=profile.batch_size, shuffle=True, num_workers=num_workers)
    validation_loader = torch.utils.data.DataLoader(validation_dataset, batch_size=profile.batch_size, shuffle=False, num_workers=num_workers)
    return train_loader, validation_loader, dataset.classes


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.classifier_export import build_classifier_export_metadata
    from reposcan_contracts.config.loader import load_training_dataset_manifest, load_training_profile
    from reposcan_contracts.training import DatasetAdapter
    from reposcan_training import (
        build_run_manifest,
        ensure_dataset_review_status,
        make_run_name,
        prepare_classification_workspace,
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
    status_path = workspace_dir / "training_status.json"
    events_path = workspace_dir / "training_events.log"

    prepared_files, notes, _ = prepare_classification_workspace(repo_root, profile, dataset_manifest, workspace_dir)
    training_command = [
        str(Path(sys.executable).resolve()),
        "-u",
        str(Path(__file__).resolve()),
        "--profile",
        str(profile_path),
        "--dataset-manifest",
        str(dataset_manifest_path),
        "--run-name",
        run_name,
        "--execute",
    ]

    run_manifest = build_run_manifest(
        profile=profile,
        manifest=dataset_manifest,
        dataset_manifest_path=dataset_manifest_path,
        workspace_dir=workspace_dir,
        run_name=run_name,
        prepared_files=prepared_files,
        training_command=training_command,
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
        if not args.execute:
            print("Preparation complete. Training was not started.")
        return 0

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch and torchvision are required to execute attribute-classifier training") from exc

    if profile.dataset_adapter == DatasetAdapter.stanford_cars:
        train_loader, validation_loader, class_names = _build_stanford_cars_loaders(profile, dataset_manifest, repo_root)
    else:
        train_loader, validation_loader, class_names = _build_imagefolder_loaders(profile, dataset_manifest, repo_root)

    model = _build_torchvision_model(profile.base_model, num_classes=len(class_names))
    device = torch.device("cuda" if torch.cuda.is_available() and profile.device != "cpu" else "cpu")
    model = model.to(device)
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-4)

    checkpoints_dir = workspace_dir / "checkpoints"
    exports_dir = workspace_dir / "exports"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)
    best_checkpoint = checkpoints_dir / "best.pt"
    last_checkpoint = checkpoints_dir / "last.pt"
    _write_training_status(
        status_path,
        state="running",
        run_name=run_name,
        total_epochs=profile.epochs,
        best_checkpoint=best_checkpoint if best_checkpoint.exists() else None,
    )
    _append_training_event(events_path, f"run_started total_epochs={profile.epochs} workspace={workspace_dir}")

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=profile.epochs, eta_min=1e-6
    )

    best_val = 0.0
    epochs_without_improvement = 0
    patience = profile.patience if hasattr(profile, "patience") and profile.patience else profile.epochs
    best_epoch = 0
    try:
        for epoch in range(1, profile.epochs + 1):
            print(f"starting_epoch={epoch}/{profile.epochs}")
            _append_training_event(events_path, f"epoch_started epoch={epoch}/{profile.epochs}")
            model.train()
            train_examples = 0
            train_correct = 0
            for images, labels in train_loader:
                images = images.to(device)
                labels = labels.to(device)
                logits = model(images)
                loss = criterion(logits, labels)
                preds = torch.argmax(logits, dim=1)
                train_correct += (preds == labels).sum().item()
                train_examples += labels.size(0)
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
            scheduler.step()

            train_acc = (train_correct / train_examples) if train_examples else 0.0
            val_acc = _evaluate(model, validation_loader, device)
            current_lr = scheduler.get_last_lr()[0]
            print(f"epoch={epoch} train_acc={train_acc:.4f} val_acc={val_acc:.4f} lr={current_lr:.2e}")
            torch.save({"state_dict": model.state_dict(), "classes": class_names}, last_checkpoint)
            if val_acc >= best_val:
                best_val = val_acc
                best_epoch = epoch
                epochs_without_improvement = 0
                torch.save({"state_dict": model.state_dict(), "classes": class_names}, best_checkpoint)
            else:
                epochs_without_improvement += 1

            _write_training_status(
                status_path,
                state="running",
                run_name=run_name,
                total_epochs=profile.epochs,
                current_epoch=epoch,
                train_accuracy=train_acc,
                validation_accuracy=val_acc,
                best_validation_accuracy=best_val,
                best_checkpoint=best_checkpoint if best_checkpoint.exists() else None,
            )
            _append_training_event(
                events_path,
                (
                    f"epoch_completed epoch={epoch} "
                    f"train_acc={train_acc:.4f} val_acc={val_acc:.4f} "
                    f"best_val={best_val:.4f} lr={current_lr:.2e}"
                ),
            )

            if epochs_without_improvement >= patience:
                print(f"Early stopping at epoch {epoch} (no improvement for {patience} epochs).")
                _append_training_event(events_path, f"early_stopping epoch={epoch} patience={patience}")
                break

        checkpoint = torch.load(best_checkpoint, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["state_dict"])
        model = model.to("cpu")
        model.eval()
        dummy = torch.randn(1, 3, profile.image_size, profile.image_size)
        onnx_path = exports_dir / "model.onnx"
        torch.onnx.export(
            model,
            dummy,
            onnx_path,
            input_names=["images"],
            output_names=["logits"],
            dynamic_axes={"images": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=17,
        )

        labels_path = exports_dir / "labels.json"
        labels_metadata = build_classifier_export_metadata(
            task=profile.task,
            classes=class_names,
            image_size=profile.image_size,
            base_model=profile.base_model,
        )
        labels_path.write_text(labels_metadata.model_dump_json(indent=2, by_alias=True), encoding="utf-8")

        _write_training_status(
            status_path,
            state="completed",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=best_epoch or profile.epochs,
            best_validation_accuracy=best_val,
            best_checkpoint=best_checkpoint,
            exported_onnx=onnx_path,
            label_metadata=labels_path,
        )
        _append_training_event(
            events_path,
            f"run_completed best_epoch={best_epoch or profile.epochs} best_val={best_val:.4f} onnx={onnx_path}",
        )

        print(f"Best checkpoint: {best_checkpoint}")
        print(f"Exported ONNX: {onnx_path}")
        print(f"Labels: {labels_path}")
        return 0
    except Exception as exc:
        _write_training_status(
            status_path,
            state="failed",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=best_epoch,
            best_validation_accuracy=best_val,
            best_checkpoint=best_checkpoint if best_checkpoint.exists() else None,
            error_message=str(exc),
        )
        _append_training_event(events_path, f"run_failed error={exc}")
        raise


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
