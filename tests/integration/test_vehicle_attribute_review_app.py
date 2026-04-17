from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _load_review_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "launch_vehicle_attribute_review_app.py"
    spec = importlib.util.spec_from_file_location("vehicle_attribute_review_app", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_best_suggestion_prefill_prefers_vlm_and_color():
    module = _load_review_module()
    row = {
        "reposcan_accepted": "false",
        "reposcan_reviewed": "false",
        "reposcan_oklahoma_tags": "",
        "reviewer_notes": "",
        "suggested_vlm_review_action": "accept_suggestion",
        "suggested_vlm_confidence": "0.91",
        "suggested_vlm_provider": "clip_oklahoma",
        "suggested_vlm_vehicle_make": "Ford",
        "suggested_vlm_vehicle_model_family": "F-Series",
        "suggested_vlm_vehicle_model": "F-150",
        "suggested_vlm_body_type": "pickup",
        "suggested_vehicle_color": "black",
        "suggested_vehicle_color_confidence": "0.83",
        "suggested_make_model_top1_confidence": "0.22",
        "suggested_vehicle_make": "",
        "suggested_vehicle_model": "",
    }

    prefill = module.build_best_suggestion_prefill(row)

    assert prefill["reposcan_accepted"] == "true"
    assert prefill["reposcan_vehicle_make"] == "ford"
    assert prefill["reposcan_vehicle_model"] == "f_series"
    assert prefill["reposcan_class_label"] == "ford_f_series"
    assert prefill["reposcan_vehicle_color"] == "black"
    assert "vehicle_class:pickup" in prefill["reposcan_oklahoma_tags"]
    assert "make_model:ford_f_series" in prefill["reposcan_oklahoma_tags"]
    assert "prefilled_from:clip_oklahoma" in prefill["reviewer_notes"]


def test_apply_form_to_row_normalizes_fields():
    module = _load_review_module()
    row = {"crop_id": "crop_1"}

    updated = module.apply_form_to_row(
        row,
        accepted=True,
        reviewed=False,
        class_label="Ford F-Series",
        vehicle_make="Ford",
        vehicle_model="F-Series",
        vehicle_year="2020",
        vehicle_color="Black",
        oklahoma_tags="vehicle_class:pickup|make_model:ford_f_series",
        reviewer_notes="looks good",
    )

    assert updated["reposcan_accepted"] == "true"
    assert updated["reposcan_reviewed"] == "false"
    assert updated["reposcan_class_label"] == "ford_f_series"
    assert updated["reposcan_vehicle_make"] == "ford"
    assert updated["reposcan_vehicle_model"] == "f_series"
    assert updated["reposcan_vehicle_year"] == "2020"
    assert updated["reposcan_vehicle_color"] == "black"


def test_next_pending_index_wraps():
    module = _load_review_module()
    rows = [
        {"reposcan_reviewed": "true"},
        {"reposcan_reviewed": "true"},
        {"reposcan_reviewed": "false"},
        {"reposcan_reviewed": "true"},
    ]

    assert module.next_pending_index(rows, 0, step=1) == 2
    assert module.next_pending_index(rows, 3, step=1) == 2


def test_build_best_suggestion_prefill_does_not_mutate_row():
    module = _load_review_module()
    row = {
        "reposcan_accepted": "false",
        "reposcan_reviewed": "false",
        "reposcan_oklahoma_tags": "",
        "reviewer_notes": "",
        "suggested_vlm_review_action": "accept_suggestion",
        "suggested_vlm_confidence": "0.91",
        "suggested_vlm_provider": "clip_oklahoma",
        "suggested_vlm_vehicle_make": "Ford",
        "suggested_vlm_vehicle_model_family": "F-Series",
        "suggested_vlm_body_type": "pickup",
        "suggested_vehicle_color": "black",
        "suggested_vehicle_color_confidence": "0.83",
    }
    snapshot = dict(row)

    prefill = module.build_best_suggestion_prefill(row)

    assert row == snapshot, "build_best_suggestion_prefill must not mutate the input row"
    assert prefill["reposcan_accepted"] == "true"


def test_build_reject_prefill_does_not_mutate_row():
    module = _load_review_module()
    row = {
        "reposcan_accepted": "true",
        "reposcan_reviewed": "false",
        "reposcan_class_label": "ford_f_series",
        "reposcan_vehicle_make": "ford",
        "reposcan_vehicle_model": "f_series",
        "reposcan_vehicle_year": "2020",
        "reposcan_vehicle_color": "black",
        "reposcan_oklahoma_tags": "vehicle_class:pickup",
        "reviewer_notes": "",
    }
    snapshot = dict(row)

    prefill = module.build_reject_prefill(row)

    assert row == snapshot, "build_reject_prefill must not mutate the input row"
    assert prefill["reposcan_accepted"] == "false"
    assert prefill["reposcan_reviewed"] == "true"


def test_ensure_backup_copies_original(tmp_path):
    module = _load_review_module()
    review_csv = tmp_path / "review.csv"
    with review_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["crop_id", "reposcan_reviewed"])
        writer.writerow(["crop_1", "false"])

    backup_path = module._ensure_backup(review_csv)

    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == review_csv.read_text(encoding="utf-8")
