from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


DEFAULT_MERGE_FIELDS = [
    "reposcan_accepted",
    "reposcan_reviewed",
    "reposcan_class_label",
    "reposcan_vehicle_make",
    "reposcan_vehicle_model",
    "reposcan_vehicle_year",
    "reposcan_vehicle_color",
    "reposcan_oklahoma_tags",
    "reviewer_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge reviewed vehicle attribute CSV rows into a master review CSV.")
    parser.add_argument("--master-csv", required=True, help="Full review CSV that should receive the edited values.")
    parser.add_argument("--updates-csv", required=True, help="Subset CSV containing edited review fields.")
    parser.add_argument("--output-csv", required=True, help="Destination merged CSV.")
    parser.add_argument("--key-field", default="crop_id", help="Field used to match rows between the two CSVs.")
    parser.add_argument(
        "--merge-fields",
        nargs="+",
        default=DEFAULT_MERGE_FIELDS,
        help="Fields copied from the updates CSV when a matching row exists.",
    )
    parser.add_argument(
        "--copy-extra-fields",
        nargs="*",
        default=["priority_reason"],
        help="Additional non-review fields to copy when present in the updates CSV.",
    )
    parser.add_argument("--backup-output", action="store_true", help="Create a .bak copy when overwriting an existing output CSV.")
    parser.add_argument("--overwrite", action="store_true", help="Replace the output CSV if it already exists.")
    return parser.parse_args()


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    master_csv = Path(args.master_csv).resolve()
    updates_csv = Path(args.updates_csv).resolve()
    output_csv = Path(args.output_csv).resolve()

    if output_csv.exists():
        if not args.overwrite:
            raise FileExistsError(f"output CSV already exists: {output_csv}. Pass --overwrite to replace it.")
        if args.backup_output:
            shutil.copy2(output_csv, output_csv.with_suffix(output_csv.suffix + ".bak"))

    master_rows, master_fieldnames = _read_csv(master_csv)
    update_rows, update_fieldnames = _read_csv(updates_csv)
    update_index = {
        str(row.get(args.key_field) or "").strip(): row
        for row in update_rows
        if str(row.get(args.key_field) or "").strip()
    }

    merge_fields = list(dict.fromkeys(args.merge_fields + args.copy_extra_fields))
    output_fieldnames = list(master_fieldnames)
    for field in merge_fields:
        if field in update_fieldnames and field not in output_fieldnames:
            output_fieldnames.append(field)

    updated_rows = 0
    for row in master_rows:
        key = str(row.get(args.key_field) or "").strip()
        if not key:
            continue
        update_row = update_index.get(key)
        if update_row is None:
            continue
        for field in merge_fields:
            if field in update_row:
                row[field] = update_row.get(field, "")
        updated_rows += 1

    _write_csv(output_csv, master_rows, output_fieldnames)
    print(
        {
            "master_csv": str(master_csv),
            "updates_csv": str(updates_csv),
            "output_csv": str(output_csv),
            "rows": len(master_rows),
            "updated_rows": updated_rows,
            "key_field": args.key_field,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
