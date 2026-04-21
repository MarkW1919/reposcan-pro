from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


EDITABLE_FIELDS = [
    "reposcan_accepted",
    "reposcan_reviewed",
    "class_label",
    "ocr_text",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "reviewer_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a local UI for reviewing plate OCR rows.")
    parser.add_argument("--review-csv", required=True, help="Detection review CSV to edit in place.")
    parser.add_argument("--image-root", help="Optional root for frame_relative_path when frame_source_path is absent.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7862)
    parser.add_argument("--inbrowser", action="store_true")
    return parser.parse_args()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "accepted", "approved"}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return max(int(float(value)), 0)
    except (TypeError, ValueError):
        return default


def _normalize_plate_text(value: Any) -> str:
    return _clean_text(value).upper()


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


def _output_root_from_review_csv(review_csv: Path) -> Path:
    return review_csv.parent.parent


def resolve_frame_path(row: dict[str, str], *, image_root: Path | None = None) -> Path:
    direct = _clean_text(row.get("frame_source_path"))
    if direct:
        candidate = Path(direct)
        if candidate.exists():
            return candidate
    if image_root is None:
        raise FileNotFoundError("frame_source_path is missing and no --image-root was provided")
    relative = _clean_text(row.get("frame_relative_path"))
    candidate = image_root / relative
    if not candidate.exists():
        raise FileNotFoundError(f"frame image not found: {candidate}")
    return candidate


def resolve_crop_path(review_csv: Path, row: dict[str, str]) -> Path:
    return _output_root_from_review_csv(review_csv) / _clean_text(row.get("crop_relative_path"))


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
    return (
        f"**Asset** `{_clean_text(row.get('asset_id')) or 'unknown'}`  \n"
        f"**Session** `{_clean_text(row.get('capture_session_id')) or 'unknown'}`  \n"
        f"**Timestamp** `{_clean_text(row.get('timestamp_utc')) or 'unknown'}`  \n"
        f"**Detection Confidence** `{_clean_text(row.get('confidence')) or 'n/a'}`  \n"
        f"**OCR Confidence** `{_clean_text(row.get('ocr_confidence')) or 'n/a'}`"
    )


def build_suggestions_markdown(row: dict[str, str]) -> str:
    lines = []
    ocr_text = _clean_text(row.get("ocr_text"))
    if ocr_text:
        lines.append(f"- OCR suggestion: `{ocr_text}`")
    class_label = _clean_text(row.get("class_label"))
    if class_label:
        lines.append(f"- Class label: `{class_label}`")
    lines.append(
        f"- Providers: vehicle=`{_clean_text(row.get('vehicle_detector_provider')) or 'unknown'}` "
        f"plate=`{_clean_text(row.get('plate_detector_provider')) or 'unknown'}` "
        f"ocr=`{_clean_text(row.get('ocr_provider')) or _clean_text(row.get('plate_detector_provider')) or 'unknown'}` "
        f"attr=`{_clean_text(row.get('attribute_provider')) or 'unknown'}`"
    )
    return "\n".join(lines)


def apply_form_to_row(
    row: dict[str, str],
    *,
    accepted: bool,
    reviewed: bool,
    class_label: str,
    ocr_text: str,
    bbox_x: float,
    bbox_y: float,
    bbox_w: float,
    bbox_h: float,
    reviewer_notes: str,
) -> dict[str, str]:
    updated = dict(row)
    updated["reposcan_accepted"] = str(bool(accepted)).lower()
    updated["reposcan_reviewed"] = str(bool(reviewed)).lower()
    updated["class_label"] = _clean_text(class_label)
    updated["ocr_text"] = _normalize_plate_text(ocr_text)
    updated["bbox_x"] = str(_coerce_int(bbox_x, default=_coerce_int(row.get("bbox_x"))))
    updated["bbox_y"] = str(_coerce_int(bbox_y, default=_coerce_int(row.get("bbox_y"))))
    updated["bbox_w"] = str(max(_coerce_int(bbox_w, default=_coerce_int(row.get("bbox_w"))), 1))
    updated["bbox_h"] = str(max(_coerce_int(bbox_h, default=_coerce_int(row.get("bbox_h"))), 1))
    updated["reviewer_notes"] = _clean_text(reviewer_notes)
    return updated


def _bbox_tuple(row: dict[str, str]) -> tuple[int, int, int, int]:
    x = _coerce_int(row.get("bbox_x"))
    y = _coerce_int(row.get("bbox_y"))
    w = max(_coerce_int(row.get("bbox_w")), 1)
    h = max(_coerce_int(row.get("bbox_h")), 1)
    return x, y, w, h


def render_frame_overlay(row: dict[str, str], *, image_root: Path | None = None) -> Image.Image:
    frame_path = resolve_frame_path(row, image_root=image_root)
    with Image.open(frame_path) as frame_image:
        canvas = frame_image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    x, y, w, h = _bbox_tuple(row)
    outline = "green" if _truthy(row.get("reposcan_accepted")) else ("red" if _truthy(row.get("reposcan_reviewed")) else "yellow")
    draw.rectangle((x, y, x + w, y + h), outline=outline, width=4)
    label = f"plate:{_clean_text(row.get('ocr_text')) or _clean_text(row.get('confidence'))}"
    draw.text((x + 4, max(0, y - 18)), label, fill=outline)
    return canvas


def render_crop_preview(row: dict[str, str], *, image_root: Path | None = None) -> Image.Image:
    frame_path = resolve_frame_path(row, image_root=image_root)
    with Image.open(frame_path) as frame_image:
        image = frame_image.convert("RGB")
    x, y, w, h = _bbox_tuple(row)
    left = max(0, x)
    top = max(0, y)
    right = min(image.width, x + w)
    bottom = min(image.height, y + h)
    if right <= left or bottom <= top:
        return Image.new("RGB", (max(w, 1), max(h, 1)), color=(0, 0, 0))
    return image.crop((left, top, right, bottom))


def write_crop_from_row(review_csv: Path, row: dict[str, str], *, image_root: Path | None = None) -> Path:
    crop_path = resolve_crop_path(review_csv, row)
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    crop = render_crop_preview(row, image_root=image_root)
    crop.save(crop_path)
    return crop_path


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


def create_review_app(review_csv: Path, *, image_root: Path | None = None):
    try:
        import gradio as gr
    except ImportError as exc:  # pragma: no cover - UI import guard
        raise RuntimeError("Gradio is required. Install it with `python -m pip install gradio`.") from exc

    all_rows, fieldnames = _read_csv(review_csv)
    plate_row_indexes = [index for index, row in enumerate(all_rows) if _clean_text(row.get("detection_kind")).lower() == "plate"]
    if not plate_row_indexes:
        raise ValueError(f"no plate rows found in review CSV: {review_csv}")
    for field in EDITABLE_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)
    backup_path = _ensure_backup(review_csv)

    def _plate_row(plate_index: int) -> dict[str, str]:
        return all_rows[plate_row_indexes[plate_index]]

    def row_payload(index: int):
        row = _plate_row(index)
        overlay = render_frame_overlay(row, image_root=image_root)
        crop = render_crop_preview(row, image_root=image_root)
        return (
            build_progress_summary([all_rows[i] for i in plate_row_indexes], current_index=index),
            build_metadata_markdown(row),
            build_suggestions_markdown(row),
            overlay,
            crop,
            _truthy(row.get("reposcan_accepted")),
            _truthy(row.get("reposcan_reviewed")),
            _clean_text(row.get("class_label")) or "plate",
            _clean_text(row.get("ocr_text")),
            _coerce_int(row.get("bbox_x")),
            _coerce_int(row.get("bbox_y")),
            _coerce_int(row.get("bbox_w"), default=1),
            _coerce_int(row.get("bbox_h"), default=1),
            _clean_text(row.get("reviewer_notes")),
            index,
        )

    def refresh_preview(
        index: int,
        accepted: bool,
        reviewed: bool,
        class_label: str,
        ocr_text: str,
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        reviewer_notes: str,
    ):
        preview = apply_form_to_row(
            _plate_row(index),
            accepted=accepted,
            reviewed=reviewed,
            class_label=class_label,
            ocr_text=ocr_text,
            bbox_x=bbox_x,
            bbox_y=bbox_y,
            bbox_w=bbox_w,
            bbox_h=bbox_h,
            reviewer_notes=reviewer_notes,
        )
        return (
            render_frame_overlay(preview, image_root=image_root),
            render_crop_preview(preview, image_root=image_root),
        )

    def save_current(
        index: int,
        accepted: bool,
        reviewed: bool,
        class_label: str,
        ocr_text: str,
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        reviewer_notes: str,
    ):
        row_index = plate_row_indexes[index]
        all_rows[row_index] = apply_form_to_row(
            all_rows[row_index],
            accepted=accepted,
            reviewed=reviewed,
            class_label=class_label,
            ocr_text=ocr_text,
            bbox_x=bbox_x,
            bbox_y=bbox_y,
            bbox_w=bbox_w,
            bbox_h=bbox_h,
            reviewer_notes=reviewer_notes,
        )
        write_crop_from_row(review_csv, all_rows[row_index], image_root=image_root)
        _write_csv(review_csv, all_rows, fieldnames)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return f"Saved plate row {index + 1}/{len(plate_row_indexes)} at {timestamp}. Backup: {backup_path.name}"

    def save_and_show(index: int, *form_values):
        message = save_current(index, *form_values)
        return (message, *row_payload(index))

    def save_next(index: int, *form_values):
        message = save_current(index, *form_values)
        next_index = next_pending_index([all_rows[i] for i in plate_row_indexes], index, step=1)
        return (message, *row_payload(next_index))

    def show_pending(index: int):
        next_index = next_pending_index([all_rows[i] for i in plate_row_indexes], index, step=1)
        return row_payload(next_index)

    with gr.Blocks(title=f"RepoScan Plate OCR Review - {review_csv.name}") as demo:
        gr.Markdown(f"## RepoScan Plate OCR Review\nEditing `{review_csv}`")
        status_box = gr.Textbox(label="Status", value=f"Backup created at `{backup_path.name}`", interactive=False)
        progress_markdown = gr.Markdown()
        metadata_markdown = gr.Markdown()
        suggestions_markdown = gr.Markdown()
        with gr.Row():
            frame_overlay = gr.Image(label="Frame Overlay", type="pil")
            crop_preview = gr.Image(label="Plate Crop", type="pil")
        accepted_box = gr.Checkbox(label="Accepted")
        reviewed_box = gr.Checkbox(label="Reviewed")
        class_label_box = gr.Textbox(label="Class Label", value="plate")
        ocr_text_box = gr.Textbox(label="OCR Text")
        with gr.Row():
            bbox_x_box = gr.Number(label="bbox_x", precision=0)
            bbox_y_box = gr.Number(label="bbox_y", precision=0)
            bbox_w_box = gr.Number(label="bbox_w", precision=0)
            bbox_h_box = gr.Number(label="bbox_h", precision=0)
        reviewer_notes_box = gr.Textbox(label="Reviewer Notes", lines=3)
        current_index = gr.Number(label="Row Index", value=0, precision=0, visible=False)

        preview_inputs = [
            current_index,
            accepted_box,
            reviewed_box,
            class_label_box,
            ocr_text_box,
            bbox_x_box,
            bbox_y_box,
            bbox_w_box,
            bbox_h_box,
            reviewer_notes_box,
        ]

        for component in [accepted_box, reviewed_box, class_label_box, ocr_text_box, bbox_x_box, bbox_y_box, bbox_w_box, bbox_h_box, reviewer_notes_box]:
            component.change(refresh_preview, inputs=preview_inputs, outputs=[frame_overlay, crop_preview])

        with gr.Row():
            save_button = gr.Button("Save")
            save_next_button = gr.Button("Save + Next")
            next_pending_button = gr.Button("Next Pending")

        save_button.click(
            save_and_show,
            inputs=preview_inputs,
            outputs=[
                status_box,
                progress_markdown,
                metadata_markdown,
                suggestions_markdown,
                frame_overlay,
                crop_preview,
                accepted_box,
                reviewed_box,
                class_label_box,
                ocr_text_box,
                bbox_x_box,
                bbox_y_box,
                bbox_w_box,
                bbox_h_box,
                reviewer_notes_box,
                current_index,
            ],
        )
        save_next_button.click(
            save_next,
            inputs=preview_inputs,
            outputs=[
                status_box,
                progress_markdown,
                metadata_markdown,
                suggestions_markdown,
                frame_overlay,
                crop_preview,
                accepted_box,
                reviewed_box,
                class_label_box,
                ocr_text_box,
                bbox_x_box,
                bbox_y_box,
                bbox_w_box,
                bbox_h_box,
                reviewer_notes_box,
                current_index,
            ],
        )
        next_pending_button.click(
            show_pending,
            inputs=[current_index],
            outputs=[
                progress_markdown,
                metadata_markdown,
                suggestions_markdown,
                frame_overlay,
                crop_preview,
                accepted_box,
                reviewed_box,
                class_label_box,
                ocr_text_box,
                bbox_x_box,
                bbox_y_box,
                bbox_w_box,
                bbox_h_box,
                reviewer_notes_box,
                current_index,
            ],
        )

        demo.load(
            row_payload,
            inputs=[current_index],
            outputs=[
                progress_markdown,
                metadata_markdown,
                suggestions_markdown,
                frame_overlay,
                crop_preview,
                accepted_box,
                reviewed_box,
                class_label_box,
                ocr_text_box,
                bbox_x_box,
                bbox_y_box,
                bbox_w_box,
                bbox_h_box,
                reviewer_notes_box,
                current_index,
            ],
        )

    return demo


def main() -> int:
    args = parse_args()
    review_csv = Path(args.review_csv).resolve()
    image_root = Path(args.image_root).resolve() if args.image_root else None
    app = create_review_app(review_csv, image_root=image_root)
    app.launch(server_name=args.host, server_port=args.port, inbrowser=args.inbrowser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
