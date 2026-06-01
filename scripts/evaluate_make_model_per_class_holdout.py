"""Per-class holdout evaluation for a single make/model classifier checkpoint.

The trainer already reports an aggregate holdout accuracy, but that single
number hides whether newly-added classes are actually usable. This script
reuses the exact validation preprocessing the trainer uses (Resize to
image_size, ToTensor, ImageNet normalize) and the same checkpoint format
(``{"classes": [...], "state_dict": {...}}``), then reports:

  * overall holdout accuracy (sanity-check against the trainer's number)
  * per-class accuracy, sorted worst-first
  * for each class, the single most common wrong prediction (top confusion)

It is intentionally standalone and read-only: it loads ``best.pt`` and the
holdout split, computes metrics, and writes a JSON report. It never touches
training outputs or datasets.

Usage:
    python scripts/evaluate_make_model_per_class_holdout.py \
        --checkpoint runtime/training/<run>/checkpoints/best.pt \
        --holdout-root data/curated/<dataset>/splits/holdout \
        --image-size 260 \
        --output runtime/training/<run>/per_class_holdout_report.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--holdout-root", required=True, type=Path)
    parser.add_argument("--image-size", type=int, default=260)
    parser.add_argument("--base-model", default="efficientnet_b0")
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--output", type=Path, default=None)
    # Optional: comma-separated list of classes to flag as "new" in the
    # report so the summary can call out whether the expansion landed.
    parser.add_argument("--new-classes", default="")
    return parser.parse_args()


def _module_from_path(model, path: str):
    node = model
    for part in path.split("."):
        node = getattr(node, part)
    return node


def _replace_module(model, path: str, new_module) -> None:
    parts = path.split(".")
    parent = model
    for part in parts[:-1]:
        parent = getattr(parent, part)
    setattr(parent, parts[-1], new_module)


def _build_model(base_model: str, *, num_classes: int, dropout: float):
    import torch
    from torchvision import models

    supported = {
        "resnet18": ("resnet18", "fc"),
        "resnet50": ("resnet50", "fc"),
        "efficientnet_b0": ("efficientnet_b0", "classifier.1"),
        "mobilenet_v3_large": ("mobilenet_v3_large", "classifier.3"),
        "convnext_tiny": ("convnext_tiny", "classifier.2"),
    }
    name = (base_model or "efficientnet_b0").strip().lower()
    if name not in supported:
        raise ValueError(f"Unsupported base_model '{name}'.")
    constructor_name, head_path = supported[name]
    model = getattr(models, constructor_name)(weights=None)
    head = _module_from_path(model, head_path)
    in_features = head.in_features
    if dropout > 0.0:
        new_head = torch.nn.Sequential(
            torch.nn.Dropout(p=dropout),
            torch.nn.Linear(in_features, num_classes),
        )
    else:
        new_head = torch.nn.Linear(in_features, num_classes)
    _replace_module(model, head_path, new_head)
    return model


def main() -> int:
    args = parse_args()
    import torch
    from torchvision import datasets, transforms

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    class_names = list(checkpoint["classes"])
    num_classes = len(class_names)

    model = _build_model(args.base_model, num_classes=num_classes, dropout=args.dropout)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    transform = transforms.Compose(
        [
            transforms.Resize((args.image_size, args.image_size)),
            transforms.ToTensor(),
            normalize,
        ]
    )

    dataset = datasets.ImageFolder(str(args.holdout_root), transform=transform)
    holdout_classes = list(dataset.classes)
    if holdout_classes != class_names:
        # The trainer derives class index order from the train split; the
        # holdout ImageFolder derives it alphabetically. They should match
        # for this dataset, but guard against silent misalignment.
        print("WARNING: holdout class order differs from checkpoint class order.")
        print(f"  checkpoint: {class_names}")
        print(f"  holdout:    {holdout_classes}")

    loader = torch.utils.data.DataLoader(dataset, batch_size=args.batch_size, shuffle=False)

    per_class_total: dict[str, int] = defaultdict(int)
    per_class_correct: dict[str, int] = defaultdict(int)
    # confusion[true_name][pred_name] = count
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            logits = model(images)
            preds = torch.argmax(logits, dim=1)
            for i in range(labels.size(0)):
                true_name = holdout_classes[labels[i].item()]
                pred_name = class_names[preds[i].item()]
                per_class_total[true_name] += 1
                if true_name == pred_name:
                    per_class_correct[true_name] += 1
                    correct += 1
                else:
                    confusion[true_name][pred_name] += 1
                total += 1

    overall = correct / total if total else 0.0
    new_classes = {c.strip() for c in args.new_classes.split(",") if c.strip()}

    per_class = {}
    for c in holdout_classes:
        n = per_class_total[c]
        k = per_class_correct[c]
        acc = (k / n) if n else 0.0
        top_confusion = None
        if confusion[c]:
            wrong_name, wrong_count = max(confusion[c].items(), key=lambda kv: kv[1])
            top_confusion = {"predicted": wrong_name, "count": wrong_count}
        per_class[c] = {
            "accuracy": round(acc, 4),
            "correct": k,
            "total": n,
            "is_new_in_v5": c in new_classes,
            "top_confusion": top_confusion,
        }

    report = {
        "checkpoint": str(args.checkpoint),
        "holdout_root": str(args.holdout_root),
        "image_size": args.image_size,
        "overall_holdout_accuracy": round(overall, 4),
        "class_count": num_classes,
        "sample_count": total,
        "per_class": per_class,
    }

    # Print a worst-first console summary.
    ordered = sorted(per_class.items(), key=lambda kv: kv[1]["accuracy"])
    print(f"overall_holdout_acc={overall:.4f} ({correct}/{total}) classes={num_classes}")
    print()
    print(f"{'class':28s} {'acc':>6s} {'n':>4s}  new  top_confusion")
    for name, row in ordered:
        conf = row["top_confusion"]
        conf_str = f"{conf['predicted']} x{conf['count']}" if conf else "-"
        new_flag = "NEW" if row["is_new_in_v5"] else "   "
        print(f"{name:28s} {row['accuracy']*100:5.1f}% {row['total']:4d}  {new_flag}  {conf_str}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print()
        print(f"wrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
