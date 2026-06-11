from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan a capture-session-aware train/validation/holdout split.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--holdout-ratio", type=float, default=0.1)
    parser.add_argument("--field-eval-tag", action="append", default=[])
    parser.add_argument("--allow-pending", action="store_true")
    return parser.parse_args()


def _choose_split(counts: dict[str, int], targets: dict[str, float]) -> str:
    deficits = {
        name: targets[name] - counts[name]
        for name in ("train", "validation", "holdout")
    }
    return max(deficits, key=lambda name: (deficits[name], -counts[name]))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest
    from reposcan_contracts.dataset import DatasetReviewStatus, DatasetSplit, DatasetSplitAssignment, DatasetSplitManifest

    args = parse_args()
    manifest_path = repo_root / args.manifest if not Path(args.manifest).is_absolute() else Path(args.manifest)
    manifest = load_training_dataset_manifest(manifest_path)

    if not manifest.assets:
        raise ValueError("split planning requires a dataset manifest with assets")
    if manifest.review_status != DatasetReviewStatus.approved and not args.allow_pending:
        raise ValueError("split planning requires an approved dataset manifest unless --allow-pending is set")

    field_eval_tags = set(args.field_eval_tag)
    sessions: dict[str, list] = defaultdict(list)
    for asset in manifest.assets:
        sessions[asset.capture_session_id].append(asset)

    field_eval_sessions: set[str] = set()
    for session_id, assets in sessions.items():
        for asset in assets:
            asset_tags = set(asset.tags)
            if asset.field_eval_candidate or (field_eval_tags and asset_tags & field_eval_tags):
                field_eval_sessions.add(session_id)
                break

    regular_sessions = [
        (session_id, assets)
        for session_id, assets in sessions.items()
        if session_id not in field_eval_sessions
    ]
    regular_sessions.sort(key=lambda item: (-len(item[1]), item[0]))

    total_regular_assets = sum(len(assets) for _, assets in regular_sessions)
    targets = {
        "train": total_regular_assets * args.train_ratio,
        "validation": total_regular_assets * args.validation_ratio,
        "holdout": total_regular_assets * args.holdout_ratio,
    }
    split_counts = {"train": 0, "validation": 0, "holdout": 0}
    assignments: list[DatasetSplitAssignment] = []

    for session_id in sorted(field_eval_sessions):
        for asset in sessions[session_id]:
            assignments.append(
                DatasetSplitAssignment(
                    asset_id=asset.asset_id,
                    capture_session_id=asset.capture_session_id,
                    split=DatasetSplit.field_eval,
                    relative_path=asset.relative_path,
                    tags=asset.tags,
                )
            )

    for session_id, assets in regular_sessions:
        chosen = _choose_split(split_counts, targets)
        for asset in assets:
            assignments.append(
                DatasetSplitAssignment(
                    asset_id=asset.asset_id,
                    capture_session_id=asset.capture_session_id,
                    split=DatasetSplit(chosen),
                    relative_path=asset.relative_path,
                    tags=asset.tags,
                )
            )
        split_counts[chosen] += len(assets)

    split_manifest = DatasetSplitManifest(
        split_name=f"{manifest.dataset_name}-capture-session-plan",
        dataset_name=manifest.dataset_name,
        dataset_version=manifest.dataset_version,
        source_manifest_path=str(manifest_path),
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        holdout_ratio=args.holdout_ratio,
        field_eval_tags=sorted(field_eval_tags),
        assignments=assignments,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(split_manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )

    counts: dict[str, int] = defaultdict(int)
    for assignment in assignments:
        counts[assignment.split.value] += 1

    print(f"Split plan written to: {output_path}")
    for split_name in ("train", "validation", "holdout", "field_eval"):
        print(f"- {split_name}: {counts.get(split_name, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
