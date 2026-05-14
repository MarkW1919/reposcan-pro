"""Evaluate the v1 + v4 dispatch-ensemble make/model classifier.

Dispatch policy:
  1. Run both v1 (20-class) and v4 (30-class) on the same input crop.
  2. If v4 predicts one of the 10 v1-novel classes (jeep_grand_cherokee,
     jeep_wrangler, gmc_yukon, dodge_charger, dodge_durango, toyota_corolla,
     toyota_highlander, toyota_4runner, hyundai_sonata, kia_sorento):
         emit v4's prediction.
  3. Else if v1's top-1 softmax >= confidence_threshold (default 0.7):
         emit v1's prediction.
  4. Else:
         emit v4's prediction (which may be one of the shared 20 classes).
  5. If both top-1 softmax values are < unknown_threshold (default 0.4):
         emit class_label=None ("unknown"), so downstream consumers can
         surface "unknown make/model" rather than guess wrong.

This script runs the ensemble on the canonical-v4 holdout split and produces
per-class accuracy plus a confusion matrix, mirroring the per-class report we
already have for v1, v3, and v4 individually.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch
from torchvision import datasets, models, transforms


V1_NOVEL_CLASSES = {
    "jeep_grand_cherokee",
    "jeep_wrangler",
    "gmc_yukon",
    "dodge_charger",
    "dodge_durango",
    "toyota_corolla",
    "toyota_highlander",
    "toyota_4runner",
    "hyundai_sonata",
    "kia_sorento",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate v1+v4 dispatch ensemble.")
    parser.add_argument(
        "--v1-checkpoint",
        default="runtime/training/vehicle-make-model-canonical-v1_20260506_run1/checkpoints/best.pt",
    )
    parser.add_argument(
        "--v4-checkpoint",
        default="runtime/training/vehicle-make-model-canonical-v4_20260510_run1/checkpoints/best.pt",
    )
    parser.add_argument(
        "--holdout-root",
        default="data/curated/canonical_vehicle_make_model_20260510/splits/holdout",
    )
    parser.add_argument(
        "--report-path",
        default="runtime/training/dispatch_ensemble_v1_v4/per_class_holdout_report.json",
    )
    parser.add_argument("--confidence-threshold", type=float, default=0.7)
    parser.add_argument("--unknown-threshold", type=float, default=0.4)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def _load_classifier(checkpoint_path: Path, dropout: float = 0.3):
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    classes = list(ckpt["classes"])
    state_dict = ckpt["state_dict"]
    model = models.efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = torch.nn.Sequential(
        torch.nn.Dropout(p=dropout),
        torch.nn.Linear(in_features, len(classes)),
    )
    model.load_state_dict(state_dict)
    model.eval()
    return model, classes


def main() -> int:
    args = parse_args()

    v1_model, v1_classes = _load_classifier(Path(args.v1_checkpoint))
    v4_model, v4_classes = _load_classifier(Path(args.v4_checkpoint))
    v1_class_set = set(v1_classes)

    xform = transforms.Compose([
        transforms.Resize(290),
        transforms.CenterCrop(260),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    ds = datasets.ImageFolder(args.holdout_root, transform=xform)
    loader = torch.utils.data.DataLoader(
        ds, batch_size=args.batch_size, shuffle=False, num_workers=0,
    )

    # ds.classes lists holdout folder names (the v4 30-class taxonomy)
    holdout_classes = list(ds.classes)
    total = 0
    correct = 0
    unknown = 0
    per_class_total: dict[str, int] = defaultdict(int)
    per_class_correct: dict[str, int] = defaultdict(int)
    per_class_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    softmax = torch.nn.Softmax(dim=1)

    with torch.no_grad():
        for images, labels in loader:
            v1_probs = softmax(v1_model(images))
            v4_probs = softmax(v4_model(images))
            v1_top_p, v1_top_idx = v1_probs.max(dim=1)
            v4_top_p, v4_top_idx = v4_probs.max(dim=1)
            for i in range(len(labels)):
                true_name = holdout_classes[labels[i].item()]
                v1_pred = v1_classes[v1_top_idx[i].item()]
                v4_pred = v4_classes[v4_top_idx[i].item()]
                v1_conf = v1_top_p[i].item()
                v4_conf = v4_top_p[i].item()

                # Dispatch policy
                if v4_pred in V1_NOVEL_CLASSES:
                    chosen = v4_pred
                    source = "v4_novel"
                elif v1_conf >= args.confidence_threshold:
                    chosen = v1_pred
                    source = "v1_confident"
                elif v1_conf < args.unknown_threshold and v4_conf < args.unknown_threshold:
                    chosen = None
                    source = "unknown_both_low"
                else:
                    chosen = v4_pred if v4_conf > v1_conf else v1_pred
                    source = "v4_fallback" if v4_conf > v1_conf else "v1_fallback"

                total += 1
                per_class_total[true_name] += 1
                per_class_source[true_name][source] += 1
                if chosen is None:
                    unknown += 1
                    confusion[true_name]["__unknown__"] += 1
                else:
                    confusion[true_name][chosen] += 1
                    if chosen == true_name:
                        correct += 1
                        per_class_correct[true_name] += 1

    overall = correct / total if total else 0.0
    print(f"overall_holdout_acc={overall:.4f} ({correct}/{total}, unknown={unknown})")
    print()
    print(f'{"class":28} {"acc":>6} {"correct/total":>14}  top_confusion (sources)')
    print("-" * 110)
    report: dict[str, Any] = {
        "overall_acc": overall,
        "total": total,
        "correct": correct,
        "unknown": unknown,
        "confidence_threshold": args.confidence_threshold,
        "unknown_threshold": args.unknown_threshold,
        "per_class": {},
    }
    for c in holdout_classes:
        n = per_class_total[c]
        k = per_class_correct[c]
        if n == 0:
            continue
        acc = k / n
        others = sorted(
            [(p, cnt) for p, cnt in confusion[c].items() if p != c],
            key=lambda x: -x[1],
        )[:2]
        confstr = ", ".join(f"{p}({cnt})" for p, cnt in others) if others else "-"
        sources = ", ".join(
            f"{s}={cnt}" for s, cnt in sorted(per_class_source[c].items(), key=lambda kv: -kv[1])
        )
        print(f"{c:28} {acc:>6.3f} {k:>5}/{n:<8}  {confstr}  [{sources}]")
        report["per_class"][c] = {
            "accuracy": acc,
            "correct": k,
            "total": n,
            "top_confusions": dict(others),
            "dispatch_sources": dict(per_class_source[c]),
        }

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
