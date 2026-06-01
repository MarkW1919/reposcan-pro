"""Measure canonical-v5 make/model holdout accuracy WITH re-rank dispatch.

This answers the open caveat in VEHICLE_RECOGNITION_PIPELINE_STATUS.md: does
the Jeep / GM-full-size-SUV re-rank dispatch still help now that v5 changed
the confusion structure (40 classes instead of v4's 30)?

Dispatch policy (mirrors reposcan_inference.deferred_recognition exactly):
  1. Run the v5 primary on the crop.
  2. If v5's top-1 is one of a re-rank head's trigger classes, run that
     specialist and take ITS top-1 as the final prediction.
  3. Otherwise keep v5's prediction.

Preprocessing is Resize((260,260)) + ImageNet normalize — identical to the
trainer's validation transform and to evaluate_make_model_per_class_holdout.py
(which reproduced the trainer's 86.33% holdout exactly), so the dispatch number
here is directly comparable to the v5-alone baseline.

Read-only: loads checkpoints + holdout split, prints + writes a JSON report.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch
from torchvision import datasets, models, transforms


# Each re-rank head: the trigger classes (v5 primary predictions that dispatch
# to it). The head's own class set is read from its checkpoint.
RERANK_HEADS = [
    {
        "name": "gm-fullsize-suv",
        "checkpoint": "runtime/training/vehicle-rerank-gm-fullsize-suv-v1_20260512_run1/checkpoints/best.pt",
        "trigger_classes": {"chevrolet_suburban", "chevrolet_tahoe", "gmc_yukon"},
    },
    {
        "name": "jeep",
        "checkpoint": "runtime/training/vehicle-rerank-jeep-realonly-v1_20260514_run1/checkpoints/best.pt",
        "trigger_classes": {"jeep_grand_cherokee", "jeep_wrangler"},
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate v5 + re-rank dispatch on the v5 holdout.")
    parser.add_argument(
        "--v5-checkpoint",
        default="runtime/training/vehicle-make-model-canonical-v5_20260519_run1/checkpoints/best.pt",
    )
    parser.add_argument(
        "--holdout-root",
        default="data/curated/canonical_vehicle_make_model_20260519/splits/holdout",
    )
    parser.add_argument(
        "--report-path",
        default="runtime/training/vehicle-make-model-canonical-v5_20260519_run1/dispatch_holdout_report.json",
    )
    parser.add_argument("--image-size", type=int, default=260)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def _load_classifier(checkpoint_path: Path, dropout: float = 0.3):
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    classes = list(ckpt["classes"])
    model = models.efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = torch.nn.Sequential(
        torch.nn.Dropout(p=dropout),
        torch.nn.Linear(in_features, len(classes)),
    )
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, classes


def main() -> int:
    args = parse_args()

    v5_model, v5_classes = _load_classifier(Path(args.v5_checkpoint))

    heads = []
    trigger_to_head: dict[str, int] = {}
    for idx, spec in enumerate(RERANK_HEADS):
        model, classes = _load_classifier(Path(spec["checkpoint"]))
        heads.append({"name": spec["name"], "model": model, "classes": classes})
        for trigger in spec["trigger_classes"]:
            trigger_to_head[trigger] = idx

    xform = transforms.Compose([
        transforms.Resize((args.image_size, args.image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    ds = datasets.ImageFolder(args.holdout_root, transform=xform)
    loader = torch.utils.data.DataLoader(ds, batch_size=args.batch_size, shuffle=False, num_workers=0)
    holdout_classes = list(ds.classes)

    softmax = torch.nn.Softmax(dim=1)

    total = 0
    correct_dispatch = 0
    correct_v5_only = 0
    per_class_total: dict[str, int] = defaultdict(int)
    per_class_correct_dispatch: dict[str, int] = defaultdict(int)
    per_class_correct_v5: dict[str, int] = defaultdict(int)
    per_class_reranked: dict[str, int] = defaultdict(int)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    with torch.no_grad():
        for images, labels in loader:
            v5_probs = softmax(v5_model(images))
            _, v5_top_idx = v5_probs.max(dim=1)

            # Precompute head outputs for the whole batch (cheap on small heads).
            head_top = []
            for head in heads:
                _, top_idx = softmax(head["model"](images)).max(dim=1)
                head_top.append(top_idx)

            for i in range(len(labels)):
                true_name = holdout_classes[labels[i].item()]
                v5_pred = v5_classes[v5_top_idx[i].item()]

                final = v5_pred
                head_idx = trigger_to_head.get(v5_pred)
                if head_idx is not None:
                    head = heads[head_idx]
                    final = head["classes"][head_top[head_idx][i].item()]
                    if final != v5_pred:
                        per_class_reranked[true_name] += 1

                total += 1
                per_class_total[true_name] += 1
                confusion[true_name][final] += 1
                if v5_pred == true_name:
                    correct_v5_only += 1
                    per_class_correct_v5[true_name] += 1
                if final == true_name:
                    correct_dispatch += 1
                    per_class_correct_dispatch[true_name] += 1

    overall_dispatch = correct_dispatch / total if total else 0.0
    overall_v5 = correct_v5_only / total if total else 0.0

    print(f"v5 alone        : {overall_v5:.4f} ({correct_v5_only}/{total})")
    print(f"v5 + re-rank    : {overall_dispatch:.4f} ({correct_dispatch}/{total})")
    print(f"net delta       : {(overall_dispatch - overall_v5) * 100:+.2f} pp")
    print()
    print("Dispatch-affected classes (trigger set members):")
    print(f"  {'class':24s} {'v5':>6s} {'+rerank':>8s} {'n':>4s} {'reranked':>9s}")
    affected = sorted(trigger_to_head.keys())
    for c in affected:
        n = per_class_total[c]
        if n == 0:
            continue
        a5 = per_class_correct_v5[c] / n
        ad = per_class_correct_dispatch[c] / n
        print(f"  {c:24s} {a5*100:5.1f}% {ad*100:7.1f}% {n:4d} {per_class_reranked[c]:9d}")

    report: dict[str, Any] = {
        "v5_checkpoint": args.v5_checkpoint,
        "holdout_root": args.holdout_root,
        "image_size": args.image_size,
        "overall_v5_only": round(overall_v5, 4),
        "overall_v5_plus_rerank": round(overall_dispatch, 4),
        "net_delta_pp": round((overall_dispatch - overall_v5) * 100, 2),
        "total": total,
        "rerank_heads": [
            {"name": spec["name"], "trigger_classes": sorted(spec["trigger_classes"])}
            for spec in RERANK_HEADS
        ],
        "per_class": {},
    }
    for c in holdout_classes:
        n = per_class_total[c]
        if n == 0:
            continue
        report["per_class"][c] = {
            "v5_accuracy": round(per_class_correct_v5[c] / n, 4),
            "dispatch_accuracy": round(per_class_correct_dispatch[c] / n, 4),
            "total": n,
            "reranked_count": per_class_reranked[c],
            "is_trigger_class": c in trigger_to_head,
        }

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
