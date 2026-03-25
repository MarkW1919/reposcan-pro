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
    parser = argparse.ArgumentParser(description="Export a detection evidence package for operator handoff.")
    parser.add_argument("--detection-id", required=True)
    parser.add_argument("--deployment-config", default="configs/deployments/local-dev.yaml")
    parser.add_argument("--metadata-root", default="runtime/storage")
    parser.add_argument("--media-root")
    parser.add_argument("--output-path")
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
    output_path = Path(args.output_path) if args.output_path else None
    if output_path is not None and not output_path.is_absolute():
        output_path = repo_root / output_path

    service = StorageService(
        repository=JsonFileStorageRepository(repo_root / args.metadata_root),
        media_root=media_root if media_root.is_absolute() else repo_root / media_root,
        deployment_config=deployment,
    )
    export_result = service.export_detection_package(
        args.detection_id,
        destination_path=output_path,
    )
    payload = {
        "detection_id": export_result.detection_id,
        "export_path": str(export_result.export_path),
        "included_files": export_result.included_files,
        "missing_files": export_result.missing_files,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"export path: {export_result.export_path}")
        print(f"included files: {export_result.included_files}")
        print(f"missing files: {export_result.missing_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
