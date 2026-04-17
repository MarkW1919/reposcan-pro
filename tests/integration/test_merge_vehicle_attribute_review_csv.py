from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _load_merge_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "merge_vehicle_attribute_review_csv.py"
    spec = importlib.util.spec_from_file_location("merge_vehicle_attribute_review_csv", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_review_csv_updates_master_rows(tmp_path, monkeypatch):
    module = _load_merge_module()
    master_csv = tmp_path / "master.csv"
    updates_csv = tmp_path / "updates.csv"
    output_csv = tmp_path / "merged.csv"

    with master_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["crop_id", "source_label", "reposcan_accepted", "reposcan_reviewed", "reviewer_notes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "crop_id": "crop_1",
                "source_label": "Car",
                "reposcan_accepted": "false",
                "reposcan_reviewed": "false",
                "reviewer_notes": "",
            }
        )
        writer.writerow(
            {
                "crop_id": "crop_2",
                "source_label": "Truck",
                "reposcan_accepted": "false",
                "reposcan_reviewed": "false",
                "reviewer_notes": "",
            }
        )

    with updates_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "crop_id",
                "reposcan_accepted",
                "reposcan_reviewed",
                "reviewer_notes",
                "priority_reason",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "crop_id": "crop_2",
                "reposcan_accepted": "true",
                "reposcan_reviewed": "true",
                "reviewer_notes": "accepted",
                "priority_reason": "clip_accept",
            }
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "merge_vehicle_attribute_review_csv.py",
            "--master-csv",
            str(master_csv),
            "--updates-csv",
            str(updates_csv),
            "--output-csv",
            str(output_csv),
        ],
    )

    result = module.main()

    assert result == 0
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8", newline="")))
    assert rows[0]["reposcan_accepted"] == "false"
    assert rows[1]["reposcan_accepted"] == "true"
    assert rows[1]["reposcan_reviewed"] == "true"
    assert rows[1]["reviewer_notes"] == "accepted"
    assert rows[1]["priority_reason"] == "clip_accept"
