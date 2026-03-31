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
        description="Build a canonical vehicle make/model/year catalog for recognition training from a markdown or CSV seed list.",
    )
    parser.add_argument("--seed", required=True, help="Markdown or CSV seed file with Year/Make/Model columns.")
    parser.add_argument("--output", required=True, help="Output catalog path (.yaml or .json).")
    parser.add_argument("--catalog-name", default="us-vehicle-recognition-catalog")
    parser.add_argument("--cache-dir", default="runtime/vehicle_catalog_cache")
    parser.add_argument("--overrides", help="Optional YAML override file with aliases and explicit source-model names.")
    parser.add_argument("--labels-csv", help="Optional CSV export of expanded per-year training labels.")
    parser.add_argument(
        "--placeholder-mode",
        choices=["preserve", "listed", "make-all-models"],
        default="preserve",
        help="How to handle placeholder 'all models from database coverage' rows.",
    )
    parser.add_argument(
        "--expanded-seed-csv",
        help="Optional CSV export of explicit seed rows after placeholder expansion.",
    )
    parser.add_argument("--offline-cache-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_training import (
        build_vehicle_recognition_catalog,
        expand_vehicle_seed_entries,
        fetch_nhtsa_models_for_make_year,
        load_vehicle_catalog_overrides,
        load_vehicle_seed_entries,
        write_vehicle_recognition_catalog,
        write_vehicle_recognition_labels_csv,
        write_vehicle_seed_entries_csv,
    )

    args = parse_args()
    seed_path = Path(args.seed)
    output_path = Path(args.output)
    cache_dir = Path(args.cache_dir)
    if not seed_path.is_absolute():
        seed_path = (repo_root / seed_path).resolve()
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    if not cache_dir.is_absolute():
        cache_dir = (repo_root / cache_dir).resolve()
    overrides = None
    if args.overrides:
        overrides_path = Path(args.overrides)
        if not overrides_path.is_absolute():
            overrides_path = (repo_root / overrides_path).resolve()
        overrides = load_vehicle_catalog_overrides(overrides_path)

    seed_entries = load_vehicle_seed_entries(seed_path)
    if args.placeholder_mode != "preserve":
        seed_entries = expand_vehicle_seed_entries(
            seed_entries,
            placeholder_mode=args.placeholder_mode,
            fetch_models_for_make_year_fn=lambda make, year: fetch_nhtsa_models_for_make_year(
                make,
                year,
                cache_dir=cache_dir,
                timeout_seconds=args.timeout_seconds,
                offline_cache_only=args.offline_cache_only,
            ),
        )
    catalog = build_vehicle_recognition_catalog(
        catalog_name=args.catalog_name,
        seed_entries=seed_entries,
        overrides=overrides,
        fetch_models_for_make_year_fn=lambda make, year: fetch_nhtsa_models_for_make_year(
            make,
            year,
            cache_dir=cache_dir,
            timeout_seconds=args.timeout_seconds,
            offline_cache_only=args.offline_cache_only,
        ),
    )

    write_vehicle_recognition_catalog(output_path, catalog)
    if args.labels_csv:
        labels_path = Path(args.labels_csv)
        if not labels_path.is_absolute():
            labels_path = (repo_root / labels_path).resolve()
        write_vehicle_recognition_labels_csv(labels_path, catalog.labels)
    if args.expanded_seed_csv:
        expanded_seed_path = Path(args.expanded_seed_csv)
        if not expanded_seed_path.is_absolute():
            expanded_seed_path = (repo_root / expanded_seed_path).resolve()
        write_vehicle_seed_entries_csv(expanded_seed_path, seed_entries)

    matched_entries = sum(1 for entry in catalog.entries if entry.status == "matched")
    partial_entries = sum(1 for entry in catalog.entries if entry.status == "partial")
    missing_entries = sum(1 for entry in catalog.entries if entry.status == "missing")
    placeholder_entries = sum(1 for entry in catalog.entries if entry.status == "placeholder")

    print(f"Catalog: {output_path}")
    print(f"Entries: {len(catalog.entries)}")
    print(f"Labels: {len(catalog.labels)}")
    print(f"Matched: {matched_entries}")
    print(f"Partial: {partial_entries}")
    print(f"Missing: {missing_entries}")
    print(f"Placeholders: {placeholder_entries}")
    if args.labels_csv:
        print(f"Labels CSV: {labels_path}")
    if args.expanded_seed_csv:
        print(f"Expanded seed CSV: {expanded_seed_path}")
    return 0


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
