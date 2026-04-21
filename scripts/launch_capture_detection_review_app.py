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
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "reviewer_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a local UI for reviewing capture detection CSV rows.")
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--image-root", help="Optional root for frame_relative_path when frame_source_path is absent.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--inbrowser", action="store_true")
    return parser.parse_args()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
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
        f"**Kind** `{_clean_text(row.get('detection_kind')) or 'unknown'}`  \n"
        f"**Session** `{_clean_text(row.get('capture_session_id')) or 'unknown'}`  \n"
        f"**Timestamp** `{_clean_text(row.get('timestamp_utc')) or 'unknown'}`  \n"
        f"**Confidence** `{_clean_text(row.get('confidence')) or 'n/a'}`  \n"
        f"**Providers** vehicle=`{_clean_text(row.get('vehicle_detector_provider')) or 'unknown'}` "
        f"plate=`{_clean_text(row.get('plate_detector_provider')) or 'unknown'}` "
        f"ocr=`{_clean_text(row.get('ocr_provider')) or _clean_text(row.get('plate_detector_provider')) or 'unknown'}` "
        f"attr=`{_clean_text(row.get('attribute_provider')) or 'unknown'}`"
    )


def build_suggestions_markdown(row: dict[str, str]) -> str:
    lines = []
    class_label = _clean_text(row.get("class_label"))
    if class_label:
        lines.append(f"- Class: `{class_label}`")
    ocr_text = _clean_text(row.get("ocr_text"))
    if ocr_text:
        lines.append(
            f"- OCR: `{ocr_text}` ({_clean_text(row.get('ocr_confidence')) or 'n/a'})"
        )
    color = _clean_text(row.get("suggested_color"))
    if color:
        lines.append(f"- Color: `{color}` ({_clean_text(row.get('suggested_color_confidence')) or 'n/a'})")
    make_label = _clean_text(row.get("suggested_make"))
    model_label = _clean_text(row.get("suggested_model"))
    if make_label or model_label:
        lines.append(
            f"- Make/Model: `{make_label}` / `{model_label}` "
            f"({ _clean_text(row.get('suggested_make_confidence')) or 'n/a' } / "
            f"{ _clean_text(row.get('suggested_model_confidence')) or 'n/a' })"
        )
    year = _clean_text(row.get("suggested_year"))
    if year:
        lines.append(f"- Year: `{year}` ({_clean_text(row.get('suggested_year_confidence')) or 'n/a'})")
    return "\n".join(lines) if lines else "- No suggestions available"


def apply_form_to_row(
    row: dict[str, str],
    *,
    accepted: bool,
    reviewed: bool,
    class_label: str,
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
    label = f"{_clean_text(row.get('class_label')) or _clean_text(row.get('detection_kind'))}:{_clean_text(row.get('confidence'))}"
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
        overlay = render_frame_overlay(row, image_root=image_root)
        crop = render_crop_preview(row, image_root=image_root)
        return (
            build_progress_summary(rows, current_index=index),
            build_metadata_markdown(row),
            build_suggestions_markdown(row),
            overlay,
            crop,
            _truthy(row.get("reposcan_accepted")),
            _truthy(row.get("reposcan_reviewed")),
            _clean_text(row.get("class_label")),
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
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        reviewer_notes: str,
    ):
        preview = apply_form_to_row(
            rows[index],
            accepted=accepted,
            reviewed=reviewed,
            class_label=class_label,
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
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        reviewer_notes: str,
    ):
        rows[index] = apply_form_to_row(
            rows[index],
            accepted=accepted,
            reviewed=reviewed,
            class_label=class_label,
            bbox_x=bbox_x,
            bbox_y=bbox_y,
            bbox_w=bbox_w,
            bbox_h=bbox_h,
            reviewer_notes=reviewer_notes,
        )
        write_crop_from_row(review_csv, rows[index], image_root=image_root)
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

    def mark_accepted(
        accepted: bool,
        reviewed: bool,
        class_label: str,
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        reviewer_notes: str,
    ):
        return (
            True,
            True,
            class_label,
            bbox_x,
            bbox_y,
            bbox_w,
            bbox_h,
            reviewer_notes,
        )

    def mark_rejected(
        accepted: bool,
        reviewed: bool,
        class_label: str,
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        reviewer_notes: str,
    ):
        return (
            False,
            True,
            class_label,
            bbox_x,
            bbox_y,
            bbox_w,
            bbox_h,
            reviewer_notes,
        )

    with gr.Blocks(title="RepoScan Capture Detection Reviewer") as app:
        gr.Markdown(f"**RepoScan Capture Detection Reviewer**  \nCSV: `{review_csv}`  \nBackup: `{backup_path}`")
        current_index = gr.State(0)

        with gr.Row():
            progress_markdown = gr.Markdown()
            metadata_markdown = gr.Markdown()

        suggestions_markdown = gr.Markdown()

        with gr.Row():
            overlay_image = gr.Image(label="Frame Overlay", type="pil", height=520)
            crop_image = gr.Image(label="Crop Preview", type="pil", height=320)

        status_text = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            jump_number = gr.Number(label="Jump To Row", precision=0, minimum=1, maximum=len(rows), value=1)
            jump_button = gr.Button("Jump")
            refresh_button = gr.Button("Refresh Preview")
            next_pending_button = gr.Button("Next Pending")

        with gr.Row():
            accepted = gr.Checkbox(label="Accepted")
            reviewed = gr.Checkbox(label="Reviewed")
            class_label = gr.Textbox(label="Class Label")

        with gr.Row():
            bbox_x = gr.Number(label="BBox X", precision=0)
            bbox_y = gr.Number(label="BBox Y", precision=0)
            bbox_w = gr.Number(label="BBox W", precision=0)
            bbox_h = gr.Number(label="BBox H", precision=0)

        reviewer_notes = gr.Textbox(label="Reviewer Notes", lines=3)

        with gr.Row():
            accept_button = gr.Button("Mark Accepted")
            reject_button = gr.Button("Mark Rejected")
            prev_button = gr.Button("Previous")
            next_button = gr.Button("Next")

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
                overlay_image,
                crop_image,
                accepted,
                reviewed,
                class_label,
                bbox_x,
                bbox_y,
                bbox_w,
                bbox_h,
                reviewer_notes,
                current_index,
            ],
        )

        nav_outputs = [
            progress_markdown,
            metadata_markdown,
            suggestions_markdown,
            overlay_image,
            crop_image,
            accepted,
            reviewed,
            class_label,
            bbox_x,
            bbox_y,
            bbox_w,
            bbox_h,
            reviewer_notes,
            current_index,
        ]
        jump_button.click(fn=jump_to, inputs=[jump_number], outputs=nav_outputs)
        prev_button.click(fn=lambda index: navigate(-1, index), inputs=[current_index], outputs=nav_outputs)
        next_button.click(fn=lambda index: navigate(1, index), inputs=[current_index], outputs=nav_outputs)
        next_pending_button.click(
            fn=lambda index: row_payload(next_pending_index(rows, index, step=1)),
            inputs=[current_index],
            outputs=nav_outputs,
        )

        preview_inputs = [
            current_index,
            accepted,
            reviewed,
            class_label,
            bbox_x,
            bbox_y,
            bbox_w,
            bbox_h,
            reviewer_notes,
        ]
        refresh_button.click(fn=refresh_preview, inputs=preview_inputs, outputs=[overlay_image, crop_image])

        toggle_inputs = [accepted, reviewed, class_label, bbox_x, bbox_y, bbox_w, bbox_h, reviewer_notes]
        toggle_outputs = [accepted, reviewed, class_label, bbox_x, bbox_y, bbox_w, bbox_h, reviewer_notes]
        accept_button.click(fn=mark_accepted, inputs=toggle_inputs, outputs=toggle_outputs)
        reject_button.click(fn=mark_rejected, inputs=toggle_inputs, outputs=toggle_outputs)

        form_inputs = [
            current_index,
            accepted,
            reviewed,
            class_label,
            bbox_x,
            bbox_y,
            bbox_w,
            bbox_h,
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
    image_root = Path(args.image_root).resolve() if args.image_root else None
    app = create_review_app(review_csv, image_root=image_root)
    app.launch(server_name=args.host, server_port=args.port, inbrowser=args.inbrowser, show_error=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
