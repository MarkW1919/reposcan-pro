from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a RepoScan Pro training dataset manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--require-approved", action="store_true")
    return parser.parse_args()


def _resolve_storage_root(repo_root: Path, storage_root: str) -> Path:
    root = Path(storage_root)
    if root.is_absolute():
        return root
    return (repo_root / root).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_training_dataset_manifest
    from reposcan_contracts.dataset import DatasetReviewStatus

    args = parse_args()
    manifest_path = repo_root / args.manifest if not Path(args.manifest).is_absolute() else Path(args.manifest)
    manifest = load_training_dataset_manifest(manifest_path)
    issues: list[str] = []

    if args.require_approved and manifest.review_status != DatasetReviewStatus.approved:
        issues.append("manifest review_status must be approved when --require-approved is set")

    storage_root = _resolve_storage_root(repo_root, manifest.storage_root)

    if args.verify_files:
        for asset in manifest.assets:
            asset_path = storage_root / asset.relative_path
            if not asset_path.exists():
                issues.append(f"missing asset file: {asset_path}")

        for split in manifest.splits:
            split_path = storage_root / split.relative_path
            if not split_path.exists():
                issues.append(f"missing split path: {split_path}")
            if split.label_path is not None:
                label_path = storage_root / split.label_path
                if not label_path.exists():
                    issues.append(f"missing split label path: {label_path}")

    print(f"Dataset: {manifest.dataset_name}")
    print(f"Task: {manifest.task.value}")
    print(f"Format: {manifest.format.value}")
    print(f"Review status: {manifest.review_status.value}")
    print(f"Storage root: {storage_root}")
    print(f"Provenance source: {manifest.provenance.source_name} ({manifest.provenance.source_kind.value})")
    if manifest.assets:
        print(f"Assets: {len(manifest.assets)}")
        print(f"Capture sessions: {len({asset.capture_session_id for asset in manifest.assets})}")
    if manifest.splits:
        for split in manifest.splits:
            sample_count = split.sample_count if split.sample_count is not None else "unknown"
            print(f"- {split.split.value}: path={split.relative_path} samples={sample_count}")

    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        return 1

    print("PASS: dataset manifest is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
