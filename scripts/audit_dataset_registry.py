"""Audit every dataset manifest under data/manifests for missing on-disk data.

Datasets live under data/, runtime/ and artifacts/, all of which are gitignored.
A previously trained dataset is "lost" when its tracked manifest still exists
but the staged or curated payload it points at has been removed from the
working tree. This script is the smoke alarm for that situation: it walks
every manifest, resolves the storage_root and per-split paths, and prints a
clear PRESENT / MISSING / EMPTY status for each, returning non-zero when any
dataset is incomplete.

Run before training, before promotion, and before any cleanup pass that might
delete data/. The intent is for the operator to never train against, or
release, a manifest whose dataset has silently disappeared.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    sys.path.insert(0, str(repo_root / "packages" / "contracts" / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifests-root",
        default="data/manifests",
        help="Directory to walk for *.yaml manifests (relative to repo root).",
    )
    parser.add_argument(
        "--require-files",
        action="store_true",
        help="Open every label file and verify it is non-empty.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit a JSON report instead of human-readable text.",
    )
    parser.add_argument(
        "--report-output",
        help="Optional path (relative to repo root unless absolute) to write a JSON report.",
    )
    return parser.parse_args()


@dataclass
class SplitStatus:
    split: str
    relative_path: str
    label_path: str | None
    storage_path_present: bool
    label_path_present: bool | None
    sample_count: int | None
    notes: list[str] = field(default_factory=list)


@dataclass
class ManifestStatus:
    manifest_path: str
    dataset_name: str | None
    dataset_version: str | None
    task: str | None
    storage_root: str
    storage_root_present: bool
    review_status: str | None
    splits: list[SplitStatus]
    issues: list[str]

    @property
    def ready(self) -> bool:
        return self.storage_root_present and not self.issues


def _resolve(repo_root: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _check_manifest(repo_root: Path, manifest_path: Path, *, require_files: bool) -> ManifestStatus:
    from reposcan_contracts.config.loader import load_training_dataset_manifest

    issues: list[str] = []
    splits: list[SplitStatus] = []

    try:
        manifest = load_training_dataset_manifest(manifest_path)
    except Exception as exc:  # noqa: BLE001 - we want every manifest to surface its own failure
        return ManifestStatus(
            manifest_path=str(manifest_path.relative_to(repo_root)),
            dataset_name=None,
            dataset_version=None,
            task=None,
            storage_root="",
            storage_root_present=False,
            review_status=None,
            splits=[],
            issues=[f"manifest failed to load: {exc}"],
        )

    storage_root = _resolve(repo_root, manifest.storage_root)
    storage_present = storage_root.exists() and storage_root.is_dir()
    if not storage_present:
        issues.append(f"storage_root missing on disk: {storage_root}")

    for split in manifest.splits:
        split_path = storage_root / split.relative_path
        label_path: Path | None = (storage_root / split.label_path) if split.label_path else None
        split_present = split_path.exists()
        if not split_present:
            issues.append(f"split path missing: {split_path}")
        notes: list[str] = []
        if split_present and split_path.is_dir():
            try:
                next(split_path.iterdir())
            except StopIteration:
                notes.append("split directory is empty")
                issues.append(f"split directory empty: {split_path}")
            except OSError as exc:
                notes.append(f"could not enumerate: {exc}")
        label_present: bool | None = None
        if label_path is not None:
            label_present = label_path.exists()
            if not label_present:
                issues.append(f"label path missing: {label_path}")
            elif require_files and label_path.is_file() and label_path.stat().st_size == 0:
                notes.append("label file is empty")
                issues.append(f"label file empty: {label_path}")
        splits.append(
            SplitStatus(
                split=split.split.value if hasattr(split.split, "value") else str(split.split),
                relative_path=split.relative_path,
                label_path=split.label_path,
                storage_path_present=split_present,
                label_path_present=label_present,
                sample_count=split.sample_count,
                notes=notes,
            )
        )

    return ManifestStatus(
        manifest_path=str(manifest_path.relative_to(repo_root)),
        dataset_name=manifest.dataset_name,
        dataset_version=manifest.dataset_version,
        task=manifest.task.value if hasattr(manifest.task, "value") else str(manifest.task),
        storage_root=str(storage_root),
        storage_root_present=storage_present,
        review_status=(
            manifest.review_status.value
            if hasattr(manifest.review_status, "value")
            else str(manifest.review_status)
        ),
        splits=splits,
        issues=issues,
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)
    args = parse_args()

    manifests_root = _resolve(repo_root, args.manifests_root)
    if not manifests_root.exists():
        print(f"ERROR: manifests root does not exist: {manifests_root}", file=sys.stderr)
        return 2

    manifest_paths = sorted(manifests_root.rglob("*.yaml"))
    statuses = [
        _check_manifest(repo_root, manifest_path, require_files=args.require_files)
        for manifest_path in manifest_paths
    ]

    payload = {
        "manifests_root": str(manifests_root.relative_to(repo_root)),
        "total_manifests": len(statuses),
        "ready_count": sum(1 for status in statuses if status.ready),
        "manifests": [asdict(status) for status in statuses],
    }

    if args.report_output:
        report_output = _resolve(repo_root, args.report_output)
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Manifests root: {payload['manifests_root']}")
        print(f"Total manifests: {payload['total_manifests']}")
        print(f"Ready manifests: {payload['ready_count']}")
        print()
        for status in statuses:
            badge = "OK   " if status.ready else "MISS "
            print(
                f"{badge} {status.manifest_path} -> {status.dataset_name} "
                f"({status.task}, review={status.review_status})"
            )
            if not status.ready:
                for issue in status.issues:
                    print(f"       ! {issue}")

    failing = [status for status in statuses if not status.ready]
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
