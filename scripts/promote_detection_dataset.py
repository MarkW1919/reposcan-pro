from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(
        description="Promote reviewed YOLO labels from a capture manifest into curated detection datasets."
    )
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--labels-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-manifest", required=True)
    parser.add_argument("--field-eval-manifest")
    parser.add_argument("--dataset-name")
    parser.add_argument("--dataset-version")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at-utc")
    parser.add_argument("--review-notes")
    parser.add_argument("--accepted-task", action="append", default=["plate_detection"])
    parser.add_argument("--copy-mode", choices=("copy", "hardlink"), default="copy")
    parser.add_argument("--allow-pending", action="store_true")
    return parser.parse_args()


def _normalize_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_dataset_split_manifest, load_training_dataset_manifest
    from reposcan_contracts.dataset import AnnotationTask
    from reposcan_training import promote_detection_dataset

    args = parse_args()
    dataset_manifest_path = _normalize_path(repo_root, args.dataset_manifest)
    split_manifest_path = _normalize_path(repo_root, args.split_manifest)
    labels_root = _normalize_path(repo_root, args.labels_root)
    output_root = _normalize_path(repo_root, args.output_root)
    output_manifest = _normalize_path(repo_root, args.output_manifest)
    field_eval_manifest = _normalize_path(repo_root, args.field_eval_manifest) if args.field_eval_manifest else None

    source_manifest = load_training_dataset_manifest(dataset_manifest_path)
    split_manifest = load_dataset_split_manifest(split_manifest_path)
    dataset_name = args.dataset_name or f"{source_manifest.dataset_name}-yolo-curated"
    dataset_version = args.dataset_version or source_manifest.dataset_version
    accepted_tasks = [AnnotationTask(value) for value in dict.fromkeys(args.accepted_task)]

    result = promote_detection_dataset(
        repo_root=repo_root,
        source_manifest=source_manifest,
        source_manifest_path=dataset_manifest_path,
        split_manifest=split_manifest,
        labels_root=labels_root,
        output_root=output_root,
        dataset_manifest_path=output_manifest,
        field_eval_manifest_path=field_eval_manifest,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        reviewer=args.reviewer,
        reviewed_at_utc=args.reviewed_at_utc,
        review_notes=args.review_notes,
        allow_pending=args.allow_pending,
        copy_mode=args.copy_mode,
        accepted_tasks=accepted_tasks,
    )

    print(f"Curated dataset root: {result.dataset_root}")
    print(f"Curated manifest: {result.dataset_manifest_path}")
    for split_name in ("train", "validation", "holdout"):
        count = result.dataset_split_counts.get(split_name, 0)
        print(f"- {split_name}: {count}")
    print(f"- field_eval: {result.field_eval_count}")
    if result.field_eval_manifest_path is not None:
        print(f"Field-eval manifest: {result.field_eval_manifest_path}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
