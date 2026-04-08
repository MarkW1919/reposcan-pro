from __future__ import annotations

import argparse
import io
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
    parser.add_argument("--initial-checkpoint")
    parser.add_argument("--resume-last", action="store_true")
    parser.add_argument("--run-name")
    parser.add_argument("--export-only", action="store_true")
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


def _format_epoch_start_message(
    epoch: int,
    total_epochs: int,
    previous_epoch_summary: dict[str, object] | None = None,
) -> str:
    message = f"starting_epoch={epoch}/{total_epochs}"
    if not previous_epoch_summary:
        return message

    previous_epoch = previous_epoch_summary.get("epoch")
    train_acc = previous_epoch_summary.get("train_acc")
    val_acc = previous_epoch_summary.get("val_acc")
    best_val = previous_epoch_summary.get("best_val")
    current_lr = previous_epoch_summary.get("lr")
    parts = [message, f"prev_epoch={previous_epoch}"]
    if isinstance(train_acc, (int, float)):
        parts.append(f"train_acc={float(train_acc):.4f}")
    if isinstance(val_acc, (int, float)):
        parts.append(f"val_acc={float(val_acc):.4f}")
    if isinstance(best_val, (int, float)):
        parts.append(f"best_val={float(best_val):.4f}")
    if isinstance(current_lr, (int, float)):
        parts.append(f"lr={float(current_lr):.2e}")
    return " ".join(parts)


def _format_epoch_progress_message(
    epoch: int,
    total_epochs: int,
    batch_index: int,
    total_batches: int | None,
    running_train_acc: float,
) -> str:
    if total_batches is None:
        return f"epoch_progress epoch={epoch}/{total_epochs} batch={batch_index} train_acc={running_train_acc:.4f}"
    return (
        f"epoch_progress epoch={epoch}/{total_epochs} "
        f"batch={batch_index}/{total_batches} train_acc={running_train_acc:.4f}"
    )


def _should_emit_epoch_progress(batch_index: int, total_batches: int | None) -> bool:
    if total_batches is None or total_batches <= 0:
        return batch_index == 1
    if batch_index == 1 or batch_index == total_batches:
        return True
    interval = max(1, total_batches // 4)
    return total_batches > 4 and batch_index % interval == 0


def _load_existing_training_status(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_initial_checkpoint(*, checkpoint_path: Path, class_names: list[str]):
    import torch

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict) or "state_dict" not in checkpoint:
        raise ValueError(f"initial checkpoint '{checkpoint_path}' is missing a state_dict payload")

    checkpoint_classes = checkpoint.get("classes")
    if checkpoint_classes is not None and list(checkpoint_classes) != list(class_names):
        raise ValueError(
            "initial checkpoint classes do not match the current dataset classes"
        )
    return checkpoint["state_dict"]


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


def _export_trained_classifier(
    *,
    torch_module,
    profile,
    checkpoint_path: Path,
    exports_dir: Path,
) -> tuple[Path, Path]:
    from reposcan_contracts.classifier_export import build_classifier_export_metadata

    checkpoint = torch_module.load(checkpoint_path, map_location="cpu", weights_only=False)
    class_names = list(checkpoint["classes"])
    model = _build_torchvision_model(profile.base_model, num_classes=len(class_names))
    model.load_state_dict(checkpoint["state_dict"])
    model = model.to("cpu")
    model.eval()
    dummy = torch_module.randn(1, 3, profile.image_size, profile.image_size)
    onnx_path = exports_dir / "model.onnx"
    torch_module.onnx.export(
        model,
        dummy,
        onnx_path,
        input_names=["images"],
        output_names=["logits"],
        dynamic_axes={"images": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )

    labels_path = exports_dir / "labels.json"
    labels_metadata = build_classifier_export_metadata(
        task=profile.task,
        classes=class_names,
        image_size=profile.image_size,
        base_model=profile.base_model,
    )
    labels_path.write_text(labels_metadata.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    return onnx_path, labels_path


def _build_classification_transforms(profile, *, train: bool):
    import random

    import torch
    from PIL import Image
    from torchvision import transforms

    class RandomJpegCompression:
        def __init__(self, *, quality_range: tuple[int, int], p: float):
            self.quality_range = quality_range
            self.p = p

        def __call__(self, image):
            if random.random() > self.p:
                return image
            if not isinstance(image, Image.Image):
                return image
            quality = random.randint(*self.quality_range)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=False)
            buffer.seek(0)
            recompressed = Image.open(buffer).convert("RGB")
            return recompressed.copy()

    class AddGaussianNoise(torch.nn.Module):
        def __init__(self, *, std: float, p: float):
            super().__init__()
            self.std = std
            self.p = p

        def forward(self, tensor):
            if torch.rand(1).item() > self.p:
                return tensor
            noise = torch.randn_like(tensor) * self.std
            return (tensor + noise).clamp(0.0, 1.0)

    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    if not train:
        return transforms.Compose(
            [
                transforms.Resize((profile.image_size, profile.image_size)),
                transforms.ToTensor(),
                normalize,
            ]
        )

    train_transforms: list[object] = [
        transforms.RandomResizedCrop(profile.image_size, scale=(0.82, 1.0), ratio=(0.9, 1.1)),
    ]
    if profile.augmentation.horizontal_flip:
        train_transforms.append(transforms.RandomHorizontalFlip(p=0.5))
    if profile.augmentation.brightness_contrast:
        train_transforms.append(
            transforms.ColorJitter(brightness=0.18, contrast=0.18, saturation=0.12, hue=0.02)
        )
    if profile.augmentation.perspective_distortion:
        train_transforms.append(transforms.RandomPerspective(distortion_scale=0.15, p=0.2))
    if profile.augmentation.compression_artifacts:
        train_transforms.append(RandomJpegCompression(quality_range=(35, 85), p=0.25))
    if profile.augmentation.motion_blur or profile.augmentation.defocus_blur:
        train_transforms.append(
            transforms.RandomApply(
                [transforms.GaussianBlur(kernel_size=5, sigma=(0.15, 1.75))],
                p=0.18,
            )
        )
    train_transforms.append(transforms.ToTensor())
    if profile.augmentation.noise:
        train_transforms.append(AddGaussianNoise(std=0.02, p=0.25))
    train_transforms.append(normalize)
    return transforms.Compose(train_transforms)


def _wrap_subset_with_transform(subset, transform):
    class TransformSubset:
        def __init__(self, subset, transform):
            self.subset = subset
            self.transform = transform
            self.classes = getattr(getattr(subset, "dataset", None), "classes", None)

        def __len__(self):
            return len(self.subset)

        def __getitem__(self, index):
            image, target = self.subset[index]
            return self.transform(image), target

    return TransformSubset(subset, transform)


def _build_imagefolder_loaders(profile, manifest, repo_root: Path):
    import torch
    from torchvision import datasets

    from reposcan_contracts.dataset import DatasetSplit
    from reposcan_training import resolve_storage_root

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    split_map = {split.split: split for split in manifest.splits}
    train_root = storage_root / split_map[DatasetSplit.train].relative_path
    validation_split = split_map.get(DatasetSplit.validation)
    validation_root = storage_root / validation_split.relative_path if validation_split else None

    train_transform = _build_classification_transforms(profile, train=True)
    validation_transform = _build_classification_transforms(profile, train=False)

    train_dataset = datasets.ImageFolder(str(train_root), transform=train_transform)
    if validation_root is not None and validation_root.exists():
        validation_dataset = datasets.ImageFolder(str(validation_root), transform=validation_transform)
        class_names = list(train_dataset.classes)
    else:
        raw_dataset = datasets.ImageFolder(str(train_root), transform=None)
        if len(train_dataset) < 10:
            raise ValueError("imagefolder training requires at least 10 samples when no validation split is provided")
        val_size = max(1, int(len(raw_dataset) * 0.1))
        train_size = len(raw_dataset) - val_size
        train_subset, validation_subset = torch.utils.data.random_split(
            raw_dataset,
            [train_size, val_size],
            generator=torch.Generator().manual_seed(profile.seed),
        )
        train_dataset = _wrap_subset_with_transform(train_subset, train_transform)
        validation_dataset = _wrap_subset_with_transform(validation_subset, validation_transform)
        class_names = list(raw_dataset.classes)

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

    from reposcan_training import resolve_storage_root

    storage_root = resolve_storage_root(repo_root, manifest.storage_root)
    train_transform = _build_classification_transforms(profile, train=True)
    validation_transform = _build_classification_transforms(profile, train=False)

    class StanfordCarsTrainDataset(Dataset):
        def __init__(self, root: Path, *, transform):
            self.root = root
            self.transform = transform
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
            if self.transform is not None:
                image = self.transform(image)
            return image, target

    dataset = StanfordCarsTrainDataset(storage_root, transform=None)
    val_size = max(1, int(len(dataset) * 0.1))
    train_size = len(dataset) - val_size
    train_subset, validation_subset = random_split(
        dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(profile.seed),
    )
    train_dataset = _wrap_subset_with_transform(train_subset, train_transform)
    validation_dataset = _wrap_subset_with_transform(validation_subset, validation_transform)
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
    initial_checkpoint_path = None
    if args.initial_checkpoint:
        initial_checkpoint_path = (
            repo_root / args.initial_checkpoint if not Path(args.initial_checkpoint).is_absolute() else Path(args.initial_checkpoint)
        ).resolve()
    if args.resume_last and initial_checkpoint_path is not None:
        raise ValueError("--resume-last cannot be combined with --initial-checkpoint")

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
    checkpoints_dir = workspace_dir / "checkpoints"
    exports_dir = workspace_dir / "exports"
    best_checkpoint = checkpoints_dir / "best.pt"
    last_checkpoint = checkpoints_dir / "last.pt"

    existing_status: dict[str, object] = {}
    resume_completed_epochs = 0
    resume_best_val: float | None = None
    if args.resume_last:
        existing_status = _load_existing_training_status(status_path)
        if not last_checkpoint.exists():
            raise FileNotFoundError(f"resume checkpoint not found for run '{run_name}': {last_checkpoint}")
        resume_completed_epochs = int(existing_status.get("current_epoch") or 0)
        if resume_completed_epochs >= profile.epochs:
            raise ValueError(
                f"run '{run_name}' already completed {resume_completed_epochs} epochs, which meets or exceeds the configured total of {profile.epochs}"
            )
        best_val_raw = existing_status.get("best_validation_accuracy")
        if isinstance(best_val_raw, (int, float)):
            resume_best_val = float(best_val_raw)
        initial_checkpoint_path = last_checkpoint

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
    if initial_checkpoint_path is not None and not args.resume_last:
        training_command.extend(["--initial-checkpoint", str(initial_checkpoint_path)])
    if args.resume_last:
        training_command.append("--resume-last")

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

    if args.dry_run or (not args.execute and not args.export_only):
        print("Training command:")
        print(subprocess.list2cmdline(training_command))
        if not args.execute:
            print("Preparation complete. Training was not started.")
        return 0

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch and torchvision are required to execute attribute-classifier training") from exc

    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    if args.export_only:
        if not best_checkpoint.exists():
            raise FileNotFoundError(f"best checkpoint not found for export-only run: {best_checkpoint}")
        existing_status = _load_existing_training_status(status_path)
        best_validation_accuracy = existing_status.get("best_validation_accuracy")
        current_epoch = int(existing_status.get("current_epoch") or 0)
        _write_training_status(
            status_path,
            state="exporting",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=current_epoch,
            best_validation_accuracy=float(best_validation_accuracy) if isinstance(best_validation_accuracy, (int, float)) else None,
            best_checkpoint=best_checkpoint,
        )
        _append_training_event(events_path, f"export_only_started checkpoint={best_checkpoint}")
        onnx_path, labels_path = _export_trained_classifier(
            torch_module=torch,
            profile=profile,
            checkpoint_path=best_checkpoint,
            exports_dir=exports_dir,
        )
        _write_training_status(
            status_path,
            state="completed",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=current_epoch,
            best_validation_accuracy=float(best_validation_accuracy) if isinstance(best_validation_accuracy, (int, float)) else None,
            best_checkpoint=best_checkpoint,
            exported_onnx=onnx_path,
            label_metadata=labels_path,
        )
        _append_training_event(events_path, f"run_completed export_only=true onnx={onnx_path}")
        print(f"Best checkpoint: {best_checkpoint}")
        print(f"Exported ONNX: {onnx_path}")
        print(f"Labels: {labels_path}")
        return 0

    if profile.dataset_adapter == DatasetAdapter.stanford_cars:
        train_loader, validation_loader, class_names = _build_stanford_cars_loaders(profile, dataset_manifest, repo_root)
    else:
        train_loader, validation_loader, class_names = _build_imagefolder_loaders(profile, dataset_manifest, repo_root)

    model = _build_torchvision_model(profile.base_model, num_classes=len(class_names))
    if initial_checkpoint_path is not None:
        state_dict = _load_initial_checkpoint(checkpoint_path=initial_checkpoint_path, class_names=class_names)
        model.load_state_dict(state_dict, strict=True)
        if args.resume_last:
            print(f"Resuming from last checkpoint: {initial_checkpoint_path}")
        else:
            print(f"Loaded initial checkpoint: {initial_checkpoint_path}")
    device = torch.device("cuda" if torch.cuda.is_available() and profile.device != "cpu" else "cpu")
    model = model.to(device)
    criterion = torch.nn.CrossEntropyLoss(label_smoothing=profile.label_smoothing)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=profile.learning_rate,
        weight_decay=profile.weight_decay,
    )

    start_epoch = resume_completed_epochs + 1 if args.resume_last else 1
    best_val = resume_best_val if resume_best_val is not None else 0.0
    completed_epoch = resume_completed_epochs

    _write_training_status(
        status_path,
        state="running",
        run_name=run_name,
        total_epochs=profile.epochs,
        current_epoch=resume_completed_epochs,
        best_validation_accuracy=best_val if best_val > 0.0 else None,
        best_checkpoint=best_checkpoint if best_checkpoint.exists() else None,
    )
    if args.resume_last:
        _append_training_event(
            events_path,
            (
                f"run_resumed total_epochs={profile.epochs} "
                f"completed_epochs={resume_completed_epochs} next_epoch={start_epoch} "
                f"checkpoint={initial_checkpoint_path}"
            ),
        )
    else:
        _append_training_event(events_path, f"run_started total_epochs={profile.epochs} workspace={workspace_dir}")
    if initial_checkpoint_path is not None and not args.resume_last:
        _append_training_event(events_path, f"initial_checkpoint_loaded checkpoint={initial_checkpoint_path}")

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=profile.epochs, eta_min=1e-6
    )

    epochs_without_improvement = 0
    patience = profile.patience if hasattr(profile, "patience") and profile.patience else profile.epochs
    best_epoch = 0
    previous_epoch_summary: dict[str, object] | None = None
    if args.resume_last:
        previous_epoch_summary = {
            "epoch": resume_completed_epochs,
            "train_acc": existing_status.get("train_accuracy"),
            "val_acc": existing_status.get("validation_accuracy"),
            "best_val": existing_status.get("best_validation_accuracy"),
            "lr": None,
        }
    try:
        for epoch in range(start_epoch, profile.epochs + 1):
            print(_format_epoch_start_message(epoch, profile.epochs, previous_epoch_summary))
            _append_training_event(events_path, f"epoch_started epoch={epoch}/{profile.epochs}")
            model.train()
            train_examples = 0
            train_correct = 0
            try:
                total_batches = len(train_loader)
            except TypeError:
                total_batches = None
            for batch_index, (images, labels) in enumerate(train_loader, start=1):
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
                running_train_acc = (train_correct / train_examples) if train_examples else 0.0
                if _should_emit_epoch_progress(batch_index, total_batches):
                    print(_format_epoch_progress_message(epoch, profile.epochs, batch_index, total_batches, running_train_acc))
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

            completed_epoch = epoch
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
            previous_epoch_summary = {
                "epoch": epoch,
                "train_acc": train_acc,
                "val_acc": val_acc,
                "best_val": best_val,
                "lr": current_lr,
            }

            if epochs_without_improvement >= patience:
                print(f"Early stopping at epoch {epoch} (no improvement for {patience} epochs).")
                _append_training_event(events_path, f"early_stopping epoch={epoch} patience={patience}")
                break

        _append_training_event(events_path, f"export_started checkpoint={best_checkpoint}")
        onnx_path, labels_path = _export_trained_classifier(
            torch_module=torch,
            profile=profile,
            checkpoint_path=best_checkpoint,
            exports_dir=exports_dir,
        )

        _write_training_status(
            status_path,
            state="completed",
            run_name=run_name,
            total_epochs=profile.epochs,
            current_epoch=completed_epoch,
            best_validation_accuracy=best_val,
            best_checkpoint=best_checkpoint,
            exported_onnx=onnx_path,
            label_metadata=labels_path,
        )
        _append_training_event(
            events_path,
            f"run_completed completed_epoch={completed_epoch} best_val={best_val:.4f} onnx={onnx_path}",
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
            current_epoch=completed_epoch,
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
