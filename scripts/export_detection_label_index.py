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
        description="Export a label-review index from a generic capture dataset manifest."
    )
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--split-manifest")
    parser.add_argument("--allow-pending", action="store_true")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_dataset_split_manifest, load_training_dataset_manifest
    from reposcan_training import (
        build_detection_label_index_rows,
        ensure_detection_capture_manifest,
        validate_split_manifest_for_dataset,
        write_detection_label_index,
    )

    args = parse_args()
    dataset_manifest_path = Path(args.dataset_manifest)
    if not dataset_manifest_path.is_absolute():
        dataset_manifest_path = (repo_root / dataset_manifest_path).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()

    source_manifest = load_training_dataset_manifest(dataset_manifest_path)
    ensure_detection_capture_manifest(source_manifest, allow_pending=args.allow_pending)

    split_manifest = None
    if args.split_manifest:
        split_manifest_path = Path(args.split_manifest)
        if not split_manifest_path.is_absolute():
            split_manifest_path = (repo_root / split_manifest_path).resolve()
        split_manifest = load_dataset_split_manifest(split_manifest_path)
        validate_split_manifest_for_dataset(source_manifest, split_manifest)

    rows = build_detection_label_index_rows(
        repo_root=repo_root,
        source_manifest=source_manifest,
        split_manifest=split_manifest,
    )
    write_detection_label_index(output_path, rows)

    print(f"Label index written to: {output_path}")
    print(f"- rows: {len(rows)}")
    if split_manifest is not None:
        split_names = sorted({row.planned_split for row in rows if row.planned_split})
        print(f"- planned splits: {', '.join(split_names)}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
