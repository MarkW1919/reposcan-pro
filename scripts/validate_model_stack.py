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
    parser = argparse.ArgumentParser(description="Validate a RepoScan Pro model stack for runtime readiness.")
    parser.add_argument("--model-config", default="configs/models/local-onnx-runtime.yaml")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_model_config
    from reposcan_inference import validate_model_stack

    args = parse_args()
    model_stack = load_model_config(repo_root / args.model_config)
    report = validate_model_stack(model_stack)

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Model stack: {report.stack_name}")
        print(f"Ready: {'yes' if report.ready else 'no'}")
        for stage in report.stages:
            print(f"- {stage.stage}: backend={stage.backend}, ready={'yes' if stage.ready else 'no'}")
            for issue in stage.issues:
                print(f"  - {issue.severity}: {issue.message}")

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
