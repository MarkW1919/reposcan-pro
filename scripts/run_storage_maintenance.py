from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "storage" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run storage retention and pressure checks.")
    parser.add_argument("--deployment-config", default="configs/deployments/local-dev.yaml")
    parser.add_argument("--metadata-root", default="runtime/storage")
    parser.add_argument("--media-root")
    parser.add_argument("--reference-time-utc")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_deployment_config
    from reposcan_storage import JsonFileStorageRepository, StorageService

    args = parse_args()
    deployment = load_deployment_config(repo_root / args.deployment_config)
    media_root = Path(args.media_root) if args.media_root else Path(deployment.infrastructure.media_root)
    service = StorageService(
        repository=JsonFileStorageRepository(repo_root / args.metadata_root),
        media_root=media_root if media_root.is_absolute() else repo_root / media_root,
        deployment_config=deployment,
    )

    pressure = service.assess_storage_pressure()
    retention = service.sweep_media_retention(reference_time_utc=args.reference_time_utc)
    payload = {
        "storage_pressure": {
            "status": pressure.status,
            "total_bytes": pressure.total_bytes,
            "used_bytes": pressure.used_bytes,
            "free_bytes": pressure.free_bytes,
            "warning_threshold_bytes": pressure.warning_threshold_bytes,
            "minimum_threshold_bytes": pressure.minimum_threshold_bytes,
        },
        "retention": {
            "reference_time_utc": retention.reference_time_utc,
            "deleted_counts": retention.deleted_counts,
            "kept_counts": retention.kept_counts,
        },
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"storage pressure: {pressure.status} ({pressure.free_bytes} bytes free)")
        print(f"retention reference time: {retention.reference_time_utc}")
        print(f"deleted counts: {retention.deleted_counts}")
        print(f"kept counts: {retention.kept_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
