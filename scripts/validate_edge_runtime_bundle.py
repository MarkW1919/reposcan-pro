from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "apps" / "api" / "src",
        repo_root / "services" / "storage" / "src",
        repo_root / "services" / "capture" / "src",
        repo_root / "services" / "preprocessing" / "src",
        repo_root / "services" / "inference" / "src",
        repo_root / "services" / "tracking" / "src",
        repo_root / "services" / "alerting" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a promoted runtime bundle against a deployment profile.")
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--deployment-config", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_deployment_config, load_model_config
    from reposcan_inference import validate_deployment_runtime_bundle

    args = parse_args()
    model_stack = load_model_config(repo_root / args.model_config)
    deployment = load_deployment_config(repo_root / args.deployment_config)
    report = validate_deployment_runtime_bundle(model_stack, deployment)

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Deployment: {report.deployment_name}")
        print(f"Model stack: {report.stack_name}")
        print(f"Runtime ready: {'yes' if report.runtime_ready else 'no'}")
        print(f"Promotion ready: {'yes' if report.promotion_ready else 'no'}")
        print(f"Deployment ready: {'yes' if report.ready else 'no'}")
        for issue in report.issues:
            print(f"- {issue.scope}: {issue.severity}: {issue.message}")

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
