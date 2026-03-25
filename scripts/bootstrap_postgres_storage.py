from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Initialize the Postgres/PostGIS storage schema.")
    parser.add_argument("--deployment-config", default="configs/deployments/jetson-orin-edge.yaml")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.deployment import MetadataBackend
    from reposcan_contracts.config.loader import load_deployment_config
    from reposcan_storage.postgres import PostgresStorageRepository

    args = parse_args()
    deployment = load_deployment_config(repo_root / args.deployment_config)
    if deployment.infrastructure.metadata_backend != MetadataBackend.postgres:
        raise SystemExit(
            f"deployment profile {deployment.deployment_name} is not configured for metadata_backend=postgres"
        )

    repository = PostgresStorageRepository(deployment.infrastructure.postgres_url)
    print(f"Initialized Postgres storage backend for {deployment.deployment_name}")
    print(f"Repository: {type(repository).__name__}")
    print(f"DSN: {deployment.infrastructure.postgres_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
