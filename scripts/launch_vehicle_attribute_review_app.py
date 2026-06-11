from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EDITABLE_FIELDS = [
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
    parser = argparse.ArgumentParser(description="Launch a local UI for reviewing vehicle attribute crop CSV rows.")
    parser.add_argument(
        "--review-csv",
        required=True,
        help=(
            "Review CSV to edit in place. Typically the apply-consensus output, "
            "or a hand-filtered subset of it."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--inbrowser", action="store_true", help="Open the browser automatically on launch.")
    return parser.parse_args()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "accepted", "approved"}


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = [character if character.isalnum() else "_" for character in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_pipe_value(existing: str, value: str) -> str:
    value = value.strip()
    if not value:
        return existing or ""
    parts = [part for part in str(existing or "").split("|") if part]
    if value not in parts:
        parts.append(value)
    return "|".join(parts)


def _append_note(existing: str, note: str) -> str:
    note = note.strip()
    if not note:
        return existing or ""
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing} | {note}"


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


def _ensure_backup(review_csv: Path) -> Path:
    backup_path = review_csv.with_suffix(review_csv.suffix + ".bak")
    if not backup_path.exists():
        shutil.copy2(review_csv, backup_path)
    return backup_path


def build_progress_summary(rows: list[dict[str, str]], *, current_index: int) -> str:
    total = len(rows)
    reviewed = sum(1 for row in rows if _truthy(row.get("reposcan_reviewed")))
    accepted = sum(1 for row in rows if _truthy(row.get("reposcan_accepted")))
    pending = total - reviewed
    return (
        f"Row {current_index + 1}/{total}  \n"
        f"Reviewed: {reviewed}  \n"
        f"Accepted: {accepted}  \n"
        f"Pending: {pending}"
    )


def build_metadata_markdown(row: dict[str, str]) -> str:
    source = _clean_text(row.get("source_label")) or "unknown"
    crop_id = _clean_text(row.get("crop_id")) or "unknown"
    priority_reason = _clean_text(row.get("priority_reason")) or "none"
    crop_path = _clean_text(row.get("crop_filepath"))
    return (
        f"**Crop** `{crop_id}`  \n"
        f"**Source Label** `{source}`  \n"
        f"**Priority Reason** `{priority_reason}`  \n"
        f"**Image** `{crop_path}`"
    )


def build_suggestions_markdown(row: dict[str, str]) -> str:
    lines = []

    color = _clean_text(row.get("suggested_vehicle_color"))
    color_confidence = _coerce_float(row.get("suggested_vehicle_color_confidence"))
    if color:
        lines.append(f"- Heuristic color: `{color}` ({color_confidence:.2f})")

    onnx_label = _clean_text(row.get("suggested_make_model_top1"))
    onnx_confidence = _coerce_float(row.get("suggested_make_model_top1_confidence"))
    if onnx_label:
        lines.append(f"- Low-trust runtime make/model: `{onnx_label}` ({onnx_confidence:.2f})")

    vlm_provider = _clean_text(row.get("suggested_vlm_provider"))
    vlm_make = _clean_text(row.get("suggested_vlm_vehicle_make"))
    vlm_model = _clean_text(row.get("suggested_vlm_vehicle_model_family") or row.get("suggested_vlm_vehicle_model"))
    vlm_body_type = _clean_text(row.get("suggested_vlm_body_type"))
    vlm_confidence = _coerce_float(row.get("suggested_vlm_confidence"))
    vlm_action = _clean_text(row.get("suggested_vlm_review_action"))
    if vlm_provider:
        label = " ".join(part for part in [vlm_make, vlm_model] if part) or vlm_body_type or "unknown"
        lines.append(f"- {vlm_provider} suggestion: `{label}` ({vlm_confidence:.2f}, action `{vlm_action or 'none'}`)")

    error = _clean_text(row.get("suggestion_error") or row.get("vlm_label_error"))
    if error:
        lines.append(f"- Error: `{error}`")

    return "\n".join(lines) if lines else "- No suggestions available"


def build_best_suggestion_prefill(row: dict[str, str]) -> dict[str, str]:
    updated = {
        "reposcan_accepted": row.get("reposcan_accepted", "false"),
        "reposcan_reviewed": row.get("reposcan_reviewed", "false"),
        "reposcan_class_label": row.get("reposcan_class_label", ""),
        "reposcan_vehicle_make": row.get("reposcan_vehicle_make", ""),
        "reposcan_vehicle_model": row.get("reposcan_vehicle_model", ""),
        "reposcan_vehicle_year": row.get("reposcan_vehicle_year", ""),
        "reposcan_vehicle_color": row.get("reposcan_vehicle_color", ""),
        "reposcan_oklahoma_tags": row.get("reposcan_oklahoma_tags", ""),
        "reviewer_notes": row.get("reviewer_notes", ""),
    }

    source = ""
    vlm_action = _clean_text(row.get("suggested_vlm_review_action"))
    vlm_confidence = _coerce_float(row.get("suggested_vlm_confidence"))
    vlm_make = _slugify(row.get("suggested_vlm_vehicle_make"))
    vlm_model = _slugify(row.get("suggested_vlm_vehicle_model_family") or row.get("suggested_vlm_vehicle_model"))
    vlm_body_type = _slugify(row.get("suggested_vlm_body_type"))
    onnx_make = _slugify(row.get("suggested_vehicle_make"))
    onnx_model = _slugify(row.get("suggested_vehicle_model"))
    onnx_confidence = _coerce_float(row.get("suggested_make_model_top1_confidence"))
    color = _slugify(row.get("suggested_vehicle_color"))
    color_confidence = _coerce_float(row.get("suggested_vehicle_color_confidence"))

    if vlm_action == "accept_suggestion" and vlm_confidence >= 0.80 and vlm_make and vlm_model:
        updated["reposcan_vehicle_make"] = vlm_make
        updated["reposcan_vehicle_model"] = vlm_model
        updated["reposcan_class_label"] = _slugify(f"{vlm_make}_{vlm_model}")
        updated["reposcan_accepted"] = "true"
        source = _clean_text(row.get("suggested_vlm_provider")) or "vlm"
    if color and color_confidence >= 0.70:
        updated["reposcan_vehicle_color"] = color

    if updated["reposcan_vehicle_make"] and updated["reposcan_vehicle_model"]:
        make_model_slug = _slugify(f"{updated['reposcan_vehicle_make']}_{updated['reposcan_vehicle_model']}")
        updated["reposcan_oklahoma_tags"] = _append_pipe_value(
            updated["reposcan_oklahoma_tags"],
            f"make_model:{make_model_slug}",
        )
    if vlm_body_type:
        updated["reposcan_oklahoma_tags"] = _append_pipe_value(
            updated["reposcan_oklahoma_tags"],
            f"vehicle_class:{vlm_body_type}",
        )
    if source:
        updated["reviewer_notes"] = _append_note(updated["reviewer_notes"], f"prefilled_from:{source}")
    return updated


def build_reject_prefill(row: dict[str, str]) -> dict[str, str]:
    updated = {field: row.get(field, "") for field in EDITABLE_FIELDS}
    updated["reposcan_accepted"] = "false"
    updated["reposcan_reviewed"] = "true"
    updated["reviewer_notes"] = _append_note(updated.get("reviewer_notes", ""), "reviewed_rejected")
    return updated


def apply_form_to_row(
    row: dict[str, str],
    *,
    accepted: bool,
    reviewed: bool,
    class_label: str,
    vehicle_make: str,
    vehicle_model: str,
    vehicle_year: str,
    vehicle_color: str,
    oklahoma_tags: str,
    reviewer_notes: str,
) -> dict[str, str]:
    updated = dict(row)
    updated["reposcan_accepted"] = str(bool(accepted)).lower()
    updated["reposcan_reviewed"] = str(bool(reviewed or accepted)).lower()
    updated["reposcan_class_label"] = _slugify(class_label)
    updated["reposcan_vehicle_make"] = _slugify(vehicle_make)
    updated["reposcan_vehicle_model"] = _slugify(vehicle_model)
    updated["reposcan_vehicle_year"] = _clean_text(vehicle_year)
    updated["reposcan_vehicle_color"] = _slugify(vehicle_color)
    updated["reposcan_oklahoma_tags"] = _clean_text(oklahoma_tags)
    updated["reviewer_notes"] = _clean_text(reviewer_notes)
    return updated


def next_pending_index(rows: list[dict[str, str]], start_index: int, *, step: int = 1) -> int:
    if not rows:
        return 0
    count = len(rows)
    index = start_index
    for _ in range(count):
        index = (index + step) % count
        if not _truthy(rows[index].get("reposcan_reviewed")):
            return index
    return start_index


def create_review_app(review_csv: Path):
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("Gradio is required. Install it with `python -m pip install gradio`.") from exc

    rows, fieldnames = _read_csv(review_csv)
    if not rows:
        raise ValueError(f"review CSV is empty: {review_csv}")
    for field in EDITABLE_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)
    backup_path = _ensure_backup(review_csv)

    def row_payload(index: int):
        row = rows[index]
        prefill = {field: row.get(field, "") for field in EDITABLE_FIELDS}
        image_path = _clean_text(row.get("crop_filepath")) or None
        return (
            build_progress_summary(rows, current_index=index),
            build_metadata_markdown(row),
            build_suggestions_markdown(row),
            image_path,
            _truthy(prefill["reposcan_accepted"]),
            _truthy(prefill["reposcan_reviewed"]),
            prefill["reposcan_class_label"],
            prefill["reposcan_vehicle_make"],
            prefill["reposcan_vehicle_model"],
            prefill["reposcan_vehicle_year"],
            prefill["reposcan_vehicle_color"],
            prefill["reposcan_oklahoma_tags"],
            prefill["reviewer_notes"],
            index,
        )

    def save_current(
        index: int,
        accepted: bool,
        reviewed: bool,
        class_label: str,
        vehicle_make: str,
        vehicle_model: str,
        vehicle_year: str,
        vehicle_color: str,
        oklahoma_tags: str,
        reviewer_notes: str,
    ):
        rows[index] = apply_form_to_row(
            rows[index],
            accepted=accepted,
            reviewed=reviewed,
            class_label=class_label,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            vehicle_year=vehicle_year,
            vehicle_color=vehicle_color,
            oklahoma_tags=oklahoma_tags,
            reviewer_notes=reviewer_notes,
        )
        _write_csv(review_csv, rows, fieldnames)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return f"Saved row {index + 1}/{len(rows)} at {timestamp}. Backup: {backup_path.name}"

    def save_and_show(index: int, *form_values):
        message = save_current(index, *form_values)
        return (message, *row_payload(index))

    def save_and_step(step: int, index: int, *form_values):
        message = save_current(index, *form_values)
        next_index = (index + step) % len(rows)
        return (message, *row_payload(next_index))

    def save_and_next_pending(index: int, *form_values):
        message = save_current(index, *form_values)
        next_index = next_pending_index(rows, index, step=1)
        return (message, *row_payload(next_index))

    def navigate(step: int, index: int):
        next_index = (index + step) % len(rows)
        return row_payload(next_index)

    def jump_to(index_text: float):
        index = max(0, min(len(rows) - 1, int(index_text) - 1))
        return row_payload(index)

    def apply_prefill(index: int):
        # Return form values only; do not mutate rows[index]. Persistence must go
        # through an explicit Save so a prefill on row A cannot be silently
        # committed when the reviewer saves row B.
        preview = dict(rows[index])
        preview.update(build_best_suggestion_prefill(rows[index]))
        return (
            _truthy(preview["reposcan_accepted"]),
            _truthy(preview["reposcan_reviewed"]),
            preview["reposcan_class_label"],
            preview["reposcan_vehicle_make"],
            preview["reposcan_vehicle_model"],
            preview["reposcan_vehicle_year"],
            preview["reposcan_vehicle_color"],
            preview["reposcan_oklahoma_tags"],
            preview["reviewer_notes"],
        )

    def reject_prefill(index: int):
        # Same contract as apply_prefill: form-only, no in-memory persistence.
        preview = dict(rows[index])
        preview.update(build_reject_prefill(rows[index]))
        return (
            _truthy(preview["reposcan_accepted"]),
            _truthy(preview["reposcan_reviewed"]),
            preview["reposcan_class_label"],
            preview["reposcan_vehicle_make"],
            preview["reposcan_vehicle_model"],
            preview["reposcan_vehicle_year"],
            preview["reposcan_vehicle_color"],
            preview["reposcan_oklahoma_tags"],
            preview["reviewer_notes"],
        )

    with gr.Blocks(title="RepoScan Vehicle Attribute Reviewer") as app:
        gr.Markdown(f"**RepoScan Vehicle Attribute Reviewer**  \nCSV: `{review_csv}`  \nBackup: `{backup_path}`")
        current_index = gr.State(0)

        with gr.Row():
            progress_markdown = gr.Markdown()
            metadata_markdown = gr.Markdown()

        with gr.Row():
            image = gr.Image(label="Crop", type="filepath", height=520)
            with gr.Column():
                suggestions_markdown = gr.Markdown(label="Suggestions")
                status_text = gr.Textbox(label="Status", interactive=False)
                jump_number = gr.Number(label="Jump To Row", precision=0, minimum=1, maximum=len(rows), value=1)
                jump_button = gr.Button("Jump")

        with gr.Row():
            accepted = gr.Checkbox(label="Accepted")
            reviewed = gr.Checkbox(label="Reviewed")

        class_label = gr.Textbox(label="Class Label")
        with gr.Row():
            vehicle_make = gr.Textbox(label="Vehicle Make")
            vehicle_model = gr.Textbox(label="Vehicle Model / Family")
        with gr.Row():
            vehicle_year = gr.Textbox(label="Vehicle Year")
            vehicle_color = gr.Textbox(label="Vehicle Color")
        oklahoma_tags = gr.Textbox(label="Oklahoma Tags")
        reviewer_notes = gr.Textbox(label="Reviewer Notes", lines=3)

        with gr.Row():
            prefill_button = gr.Button("Apply Best Suggestions")
            reject_button = gr.Button("Mark Rejected")
        with gr.Row():
            prev_button = gr.Button("Previous")
            next_button = gr.Button("Next")
            next_pending_button = gr.Button("Next Pending")
        with gr.Row():
            save_button = gr.Button("Save")
            save_next_button = gr.Button("Save + Next")
            save_pending_button = gr.Button("Save + Next Pending")

        app.load(
            fn=lambda: ("", *row_payload(0)),
            outputs=[
                status_text,
                progress_markdown,
                metadata_markdown,
                suggestions_markdown,
                image,
                accepted,
                reviewed,
                class_label,
                vehicle_make,
                vehicle_model,
                vehicle_year,
                vehicle_color,
                oklahoma_tags,
                reviewer_notes,
                current_index,
            ],
        )

        jump_button.click(
            fn=jump_to,
            inputs=[jump_number],
            outputs=[
                progress_markdown,
                metadata_markdown,
                suggestions_markdown,
                image,
                accepted,
                reviewed,
                class_label,
                vehicle_make,
                vehicle_model,
                vehicle_year,
                vehicle_color,
                oklahoma_tags,
                reviewer_notes,
                current_index,
            ],
        )

        prefill_outputs = [
            accepted,
            reviewed,
            class_label,
            vehicle_make,
            vehicle_model,
            vehicle_year,
            vehicle_color,
            oklahoma_tags,
            reviewer_notes,
        ]
        prefill_button.click(fn=apply_prefill, inputs=[current_index], outputs=prefill_outputs)
        reject_button.click(fn=reject_prefill, inputs=[current_index], outputs=prefill_outputs)

        nav_outputs = [
            progress_markdown,
            metadata_markdown,
            suggestions_markdown,
            image,
            accepted,
            reviewed,
            class_label,
            vehicle_make,
            vehicle_model,
            vehicle_year,
            vehicle_color,
            oklahoma_tags,
            reviewer_notes,
            current_index,
        ]
        prev_button.click(fn=lambda index: navigate(-1, index), inputs=[current_index], outputs=nav_outputs)
        next_button.click(fn=lambda index: navigate(1, index), inputs=[current_index], outputs=nav_outputs)
        next_pending_button.click(
            fn=lambda index: row_payload(next_pending_index(rows, index, step=1)),
            inputs=[current_index],
            outputs=nav_outputs,
        )

        form_inputs = [
            current_index,
            accepted,
            reviewed,
            class_label,
            vehicle_make,
            vehicle_model,
            vehicle_year,
            vehicle_color,
            oklahoma_tags,
            reviewer_notes,
        ]
        save_outputs = [status_text, *nav_outputs]
        save_button.click(fn=save_and_show, inputs=form_inputs, outputs=save_outputs)
        save_next_button.click(fn=lambda *args: save_and_step(1, *args), inputs=form_inputs, outputs=save_outputs)
        save_pending_button.click(fn=save_and_next_pending, inputs=form_inputs, outputs=save_outputs)

    return app


def main() -> int:
    args = parse_args()
    review_csv = Path(args.review_csv).resolve()
    if not review_csv.exists():
        raise FileNotFoundError(f"review CSV not found: {review_csv}")
    app = create_review_app(review_csv)
    app.launch(server_name=args.host, server_port=args.port, inbrowser=args.inbrowser, show_error=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
