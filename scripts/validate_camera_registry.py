from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "capture" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and summarize RepoScan Pro camera configs for a deployed rig or local workstation."
    )
    parser.add_argument("--config-dir", default="configs/cameras", help="Directory containing camera YAML files")
    parser.add_argument("--pattern", default="*.yaml", help="Glob pattern used to discover camera config files")
    parser.add_argument("--enabled-only", action="store_true", help="Only print enabled camera registrations")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_capture import CameraRegistry

    args = parse_args()
    try:
        registry = CameraRegistry.from_directory(repo_root / args.config_dir, pattern=args.pattern)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Camera registry validation failed: {exc}", file=sys.stderr)
        return 1

    registrations = [
        registration
        for registration in registry.registrations()
        if registration.enabled or not args.enabled_only
    ]

    print(f"Camera registry valid: {len(registry.list_camera_ids())} config(s) loaded.")
    for registration in registrations:
        status = "enabled" if registration.enabled else "disabled"
        display_name = f" ({registration.display_name})" if registration.display_name else ""
        gps_suffix = f" gps={registration.gps_binding}" if registration.gps_binding else ""
        print(
            f"- {registration.camera_id}{display_name}: "
            f"{registration.source_type} -> {registration.binding}{gps_suffix} [{status}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
