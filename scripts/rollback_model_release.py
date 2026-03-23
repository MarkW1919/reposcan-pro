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
    parser = argparse.ArgumentParser(description="Rollback an external release channel to a previous accepted release.")
    parser.add_argument("--registry-root", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--to-release-id")
    parser.add_argument("--reason")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_inference import rollback_model_release

    args = parse_args()
    report = rollback_model_release(
        registry_root=_resolve_path(repo_root, args.registry_root),
        channel_name=args.channel,
        target_release_id=args.to_release_id,
        reason=args.reason,
    )

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        print(f"Channel: {report.channel.channel_name}")
        print(f"Current release: {report.channel.current_release_id}")
        print(f"Previous release: {report.channel.previous_release_id}")
        print(f"Active bundle: {report.active_release.model_config_path}")
        print(f"Channel file: {report.channel_path}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
