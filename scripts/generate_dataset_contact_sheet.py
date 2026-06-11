"""Generate a review_contact_sheet.jpg for a curated ImageFolder dataset.

Used when a new dataset lands in pending review status so a human can quickly
visually scan all imported images at a glance and approve / reject them.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a contact sheet for a curated dataset.")
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--output", default="review_contact_sheet.jpg")
    parser.add_argument("--thumb-size", type=int, default=240)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--label-height", type=int, default=18)
    return parser.parse_args()


def _collect_images(storage_root: Path) -> list[tuple[Path, str]]:
    splits_root = storage_root / "splits"
    rows: list[tuple[Path, str]] = []
    for split_dir in sorted(splits_root.iterdir()) if splits_root.exists() else []:
        if not split_dir.is_dir():
            continue
        for class_dir in sorted(split_dir.iterdir()):
            if not class_dir.is_dir():
                continue
            for image_path in sorted(class_dir.iterdir()):
                if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    continue
                rows.append((image_path, f"{split_dir.name}/{class_dir.name}/{image_path.name}"))
    return rows


def main() -> int:
    args = parse_args()
    storage_root = Path(args.storage_root).resolve()
    images = _collect_images(storage_root)
    if not images:
        print(f"No images found under {storage_root}/splits")
        return 1

    cols = max(1, args.columns)
    rows = math.ceil(len(images) / cols)
    thumb = args.thumb_size
    cell_h = thumb + args.label_height
    canvas = Image.new("RGB", (cols * thumb, rows * cell_h), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()

    for idx, (image_path, label) in enumerate(images):
        col = idx % cols
        row = idx // cols
        try:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                image.thumbnail((thumb, thumb))
                offset_x = col * thumb + (thumb - image.width) // 2
                offset_y = row * cell_h + (thumb - image.height) // 2
                canvas.paste(image, (offset_x, offset_y))
        except Exception as exc:
            draw.rectangle(
                (col * thumb, row * cell_h, (col + 1) * thumb, row * cell_h + thumb),
                outline="red",
            )
            draw.text((col * thumb + 4, row * cell_h + 4), f"err: {exc}", fill="red", font=font)
        text = label[-48:]
        draw.text(
            (col * thumb + 2, row * cell_h + thumb + 2),
            text,
            fill="black",
            font=font,
        )

    output_path = (storage_root / args.output) if not Path(args.output).is_absolute() else Path(args.output)
    canvas.save(output_path, quality=80)
    print(f"Wrote {output_path} ({len(images)} thumbnails, {cols}x{rows} grid)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
