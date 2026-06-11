from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:
    import cv2

    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False


PLATE_WIDTH = 600
PLATE_HEIGHT = 300

LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"
DIGITS = "0123456789"
OCR_ALLOWED_CHARS = set(DIGITS + "ABCDEFGHIJKLMNOPQRSTUVWXYZ")

COMMON_FONTS = [
    "arial.ttf",
    "Arial.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Bold.ttf",
    "LiberationSans-Regular.ttf",
]

SPLIT_NAMES = ("train", "validation", "holdout")

TRIBAL_NATIONS = [
    {
        "name": "CHOCTAW",
        "full_name": "Choctaw Nation of Oklahoma",
        "motto": "CHAHTA SIA HOKE!",
        "bg_color": (0, 70, 150),
        "text_color": (255, 215, 0),
        "secondary_color": (200, 160, 0),
    },
    {
        "name": "CHICKASAW",
        "full_name": "THE CHICKASAW NATION",
        "motto": "",
        "bg_color": (0, 100, 80),
        "text_color": (255, 255, 255),
        "secondary_color": (220, 220, 220),
    },
    {
        "name": "CHEROKEE",
        "full_name": "CHEROKEE NATION",
        "motto": "",
        "bg_color": (180, 50, 50),
        "text_color": (255, 255, 255),
        "secondary_color": (255, 215, 0),
    },
    {
        "name": "MUSCOGEE",
        "full_name": "Muscogee (Creek) Nation",
        "motto": "",
        "bg_color": (0, 80, 100),
        "text_color": (255, 255, 255),
        "secondary_color": (200, 200, 200),
    },
    {
        "name": "OSAGE",
        "full_name": "OSAGE NATION",
        "motto": "",
        "bg_color": (0, 0, 0),
        "text_color": (255, 215, 0),
        "secondary_color": (255, 215, 0),
    },
    {
        "name": "POTAWATOMI",
        "full_name": "Citizen Potawatomi Nation",
        "motto": "",
        "bg_color": (75, 0, 130),
        "text_color": (255, 255, 255),
        "secondary_color": (255, 255, 255),
    },
]


@dataclass(frozen=True)
class SplitPlan:
    split_name: str
    sample_count: int


def utc_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp_uint8(arr: np.ndarray) -> np.ndarray:
    return np.clip(arr, 0, 255).astype(np.uint8)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_font(size: int) -> ImageFont.ImageFont:
    for font_name in COMMON_FONTS:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def center_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    draw.text(xy, text, fill=fill, anchor="mm", font=font)


def choose_separator() -> str:
    return random.choice(["", "-", " "])


def normalize_ocr_label(text: str) -> str:
    return "".join(character for character in text.upper() if character in OCR_ALLOWED_CHARS)


def random_plate_number() -> str:
    letters = "".join(random.choices(LETTERS, k=3))
    digits = "".join(random.choices(DIGITS, k=random.choice([3, 4])))
    separator = choose_separator()
    return f"{letters}{separator}{digits}" if separator else f"{letters}{digits}"


def draw_standard_native_america(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for index in range(height):
        red = 255 - int(index * 0.3)
        green = 255 - int(index * 0.2)
        blue = 255
        draw.rectangle([0, index, width, index + 1], fill=(red, green, blue))

    stripe_height = height // 6
    draw.rectangle([0, 0, width, stripe_height], fill=(191, 0, 0))
    draw.rectangle([0, height - stripe_height, width, height], fill=(0, 0, 128))

    font_big = safe_font(40)
    draw.text((width // 2, stripe_height // 2), "OKLAHOMA", fill=(255, 255, 255), anchor="mm", font=font_big)

    center_x, center_y = width // 4, height // 2
    draw.ellipse([center_x - 20, center_y - 15, center_x + 20, center_y + 15], fill=(255, 255, 255))
    draw.line([center_x - 5, center_y, center_x - 30, center_y - 10], fill=(255, 255, 255), width=3)
    draw.line([center_x - 5, center_y, center_x - 30, center_y + 10], fill=(255, 255, 255), width=3)
    draw.line([center_x + 5, center_y, center_x + 30, center_y - 5], fill=(255, 255, 255), width=3)
    draw.line([center_x + 5, center_y, center_x + 30, center_y + 5], fill=(255, 255, 255), width=3)


def draw_standard_explore_oklahoma(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for index in range(height):
        red = 0
        green = int(100 + index * 0.3)
        blue = int(150 + index * 0.2)
        draw.rectangle([0, index, width, index + 1], fill=(red, green, blue))

    font_top = safe_font(40)
    draw.text((width // 2, 30), "EXPLORE", fill=(255, 255, 255), anchor="mt", font=font_top)
    draw.text((width // 2, 70), "OKLAHOMA", fill=(255, 255, 255), anchor="mt", font=font_top)

    font_bottom = safe_font(20)
    draw.text((width // 2, height - 25), "TRAVELOK.COM", fill=(255, 255, 255), anchor="mb", font=font_bottom)

    year = str(random.randint(2015, 2026))
    font_year = safe_font(24)
    draw.text((width - 50, height - 50), year, fill=(255, 255, 255), anchor="mm", font=font_year)


def draw_standard_red_specialty(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    draw.rectangle([0, 0, width, height], fill=(180, 40, 40))

    font_top = safe_font(28)
    draw.text((width // 2, 30), "MONTH STICKER", fill=(255, 255, 255), anchor="mt", font=font_top)

    font_state = safe_font(36)
    draw.text((width // 2, 90), "OKLAHOMA", fill=(255, 255, 255), anchor="mt", font=font_state)

    slogan = random.choice(["IMAGINE THAT", "46", ""])
    if slogan:
        font_slogan = safe_font(24)
        draw.text((width // 2, height - 40), slogan, fill=(255, 255, 255), anchor="mb", font=font_slogan)

    year = str(random.randint(2020, 2026))
    font_year = safe_font(28)
    draw.text((width - 60, height - 70), year, fill=(255, 255, 255), anchor="mm", font=font_year)


def draw_standard_butterfly(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for index in range(height):
        red = 255
        green = max(0, int(180 - index * 0.2))
        blue = max(0, int(100 - index * 0.1))
        draw.rectangle([0, index, width, index + 1], fill=(red, green, blue))

    font_hash = safe_font(40)
    draw.text((width // 2, 30), "#PLATE", fill=(0, 0, 0), anchor="mt", font=font_hash)

    font_save = safe_font(28)
    draw.text((width // 2, 90), "Save the Monarchs", fill=(0, 0, 0), anchor="mt", font=font_save)

    center_x, center_y = width - 70, height - 70
    draw.ellipse([center_x - 20, center_y - 15, center_x, center_y + 5], fill=(0, 0, 0))
    draw.ellipse([center_x, center_y - 15, center_x + 20, center_y + 5], fill=(0, 0, 0))
    draw.line([center_x - 15, center_y - 20, center_x - 25, center_y - 30], fill=(0, 0, 0), width=3)
    draw.line([center_x + 15, center_y - 20, center_x + 25, center_y - 30], fill=(0, 0, 0), width=3)

    font_bottom = safe_font(14)
    draw.text((width // 2, height - 20), "protect our pollinators", fill=(0, 0, 0), anchor="mb", font=font_bottom)


NON_TRIBAL_TEMPLATES = [
    ("native_america", draw_standard_native_america),
    ("explore_oklahoma", draw_standard_explore_oklahoma),
    ("red_specialty", draw_standard_red_specialty),
    ("butterfly", draw_standard_butterfly),
]


def draw_tribal_choctaw(draw: ImageDraw.ImageDraw, width: int, height: int, tribe: dict[str, Any]) -> str:
    draw.rectangle([0, 0, width, height], fill=tribe["bg_color"])

    font_motto = safe_font(28)
    draw.text((width // 2, 20), tribe["motto"], fill=tribe["text_color"], anchor="mt", font=font_motto)

    font_name = safe_font(20)
    draw.text((width // 2, height - 25), tribe["full_name"], fill=tribe["text_color"], anchor="mb", font=font_name)

    year = str(random.randint(20, 30))
    font_year = safe_font(24)
    draw.text((width - 60, height - 60), year, fill=tribe["text_color"], anchor="mm", font=font_year)

    registration = "".join(random.choices(DIGITS, k=random.choice([6, 7])))
    if random.random() > 0.5:
        prefix = random.choice(["R", "CA", "W", ""])
        registration = f"{prefix}{registration}"

    font_registration = safe_font(48)
    draw.text(
        (width // 2, height // 2 + 20),
        registration,
        fill=tribe["text_color"],
        anchor="mm",
        font=font_registration,
    )
    return registration


def draw_tribal_chickasaw(draw: ImageDraw.ImageDraw, width: int, height: int, tribe: dict[str, Any]) -> str:
    draw.rectangle([0, 0, width, height], fill=tribe["bg_color"])

    code = "".join(random.choices(LETTERS + DIGITS, k=4))
    font_code = safe_font(28)
    draw.text((30, height // 2), code, fill=tribe["secondary_color"], anchor="lm", font=font_code)

    font_name = safe_font(36)
    draw.text((width // 2, 50), tribe["full_name"], fill=tribe["text_color"], anchor="mt", font=font_name)

    registration = "".join(random.choices(DIGITS, k=random.choice([6, 7])))
    if random.random() > 0.5:
        prefix = random.choice(["W", "C", ""])
        registration = f"{prefix}{registration}"

    font_registration = safe_font(44)
    draw.text((width // 2, 150), registration, fill=tribe["text_color"], anchor="mm", font=font_registration)

    year = str(random.randint(20, 30))
    class_letter = random.choice(["A", "B", "C", ""])
    year_text = f"{class_letter} {year}".strip()
    font_year = safe_font(24)
    draw.text((width - 60, height - 50), year_text, fill=tribe["secondary_color"], anchor="mm", font=font_year)

    font_ok = safe_font(20)
    draw.text((width // 2, height - 20), "OKLAHOMA", fill=tribe["secondary_color"], anchor="mb", font=font_ok)
    return registration


def draw_tribal_cherokee(draw: ImageDraw.ImageDraw, width: int, height: int, tribe: dict[str, Any]) -> str:
    draw.rectangle([0, 0, width, height], fill=tribe["bg_color"])

    month = random.choice(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])
    font_month = safe_font(28)
    draw.text((30, 30), month, fill=tribe["secondary_color"], anchor="la", font=font_month)

    font_name = safe_font(32)
    draw.text((width // 2, 30), tribe["full_name"], fill=tribe["text_color"], anchor="mt", font=font_name)

    registration_part_1 = "".join(random.choices(LETTERS + DIGITS, k=random.choice([2, 3])))
    registration_part_2 = "".join(random.choices(DIGITS, k=3))
    registration = f"{registration_part_1} {registration_part_2}"

    font_registration = safe_font(44)
    draw.text((width // 2, 120), registration, fill=tribe["text_color"], anchor="mm", font=font_registration)

    line = "GWY-OKLAHOMA-SSY" if random.random() > 0.5 else "-".join(
        random.choices(["TAG", "NATION", "TRIBAL", "OK"], k=3)
    )
    font_line = safe_font(18)
    draw.text((width // 2, 180), line, fill=tribe["secondary_color"], anchor="mm", font=font_line)

    serial = "".join(random.choices(LETTERS + DIGITS, k=8))
    font_serial = safe_font(20)
    draw.text((width // 2, 230), serial, fill=tribe["secondary_color"], anchor="mm", font=font_serial)

    year = str(random.randint(2015, 2026))
    font_year = safe_font(24)
    draw.text((width - 60, height - 50), year, fill=tribe["secondary_color"], anchor="mm", font=font_year)
    return registration


def draw_tribal_generic(draw: ImageDraw.ImageDraw, width: int, height: int, tribe: dict[str, Any]) -> str:
    draw.rectangle([0, 0, width, height], fill=tribe["bg_color"])

    font_name = safe_font(32)
    draw.text((width // 2, 30), tribe["full_name"], fill=tribe["text_color"], anchor="mt", font=font_name)

    registration = "".join(random.choices(LETTERS + DIGITS, k=7))
    font_registration = safe_font(52)
    draw.text((width // 2, height // 2), registration, fill=tribe["text_color"], anchor="mm", font=font_registration)

    year = str(random.randint(20, 30))
    font_year = safe_font(24)
    draw.text((width - 60, height - 50), year, fill=tribe["secondary_color"], anchor="mm", font=font_year)
    return registration


TRIBAL_TEMPLATES = {
    "CHOCTAW": draw_tribal_choctaw,
    "CHICKASAW": draw_tribal_chickasaw,
    "CHEROKEE": draw_tribal_cherokee,
    "MUSCOGEE": draw_tribal_generic,
    "OSAGE": draw_tribal_generic,
    "POTAWATOMI": draw_tribal_generic,
}


def add_motion_blur(img: Image.Image, max_kernel_size: int = 15) -> Image.Image:
    if not CV2_AVAILABLE:
        return img

    array = np.array(img)
    kernel_size = random.randint(3, max_kernel_size)
    angle = random.uniform(0, 180)

    kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
    kernel[kernel_size // 2, :] = np.ones(kernel_size, dtype=np.float32)
    kernel /= kernel_size

    matrix = cv2.getRotationMatrix2D((kernel_size / 2, kernel_size / 2), angle, 1.0)
    kernel = cv2.warpAffine(kernel, matrix, (kernel_size, kernel_size))

    kernel_sum = kernel.sum()
    if kernel_sum > 0:
        kernel = kernel / kernel_sum

    array = cv2.filter2D(array, -1, kernel)
    return Image.fromarray(array)


def add_low_light(
    img: Image.Image,
    brightness_factor: tuple[float, float] = (0.2, 0.8),
    color_temp_shift: bool = True,
    add_noise: bool = True,
) -> Image.Image:
    array = np.array(img).astype(np.float32)

    factor = random.uniform(brightness_factor[0], brightness_factor[1])
    array *= factor

    if color_temp_shift and random.random() > 0.5:
        shift = random.choice(["blue", "red"])
        if shift == "blue":
            array[:, :, 0] *= random.uniform(0.8, 1.2)
            array[:, :, 1] *= random.uniform(0.8, 1.2)
            array[:, :, 2] *= random.uniform(1.0, 1.5)
        else:
            array[:, :, 0] *= random.uniform(1.0, 1.5)
            array[:, :, 1] *= random.uniform(0.8, 1.2)
            array[:, :, 2] *= random.uniform(0.8, 1.2)

    if add_noise and random.random() > 0.3:
        noise_std = random.uniform(10, 40)
        noise = np.random.normal(0, noise_std, array.shape).astype(np.float32)
        array += noise

    return Image.fromarray(clamp_uint8(array))


def add_distance_effect(img: Image.Image, min_scale: float = 0.3, max_scale: float = 0.9) -> Image.Image:
    scale = random.uniform(min_scale, max_scale)
    new_width = max(32, int(PLATE_WIDTH * scale))
    new_height = max(16, int(PLATE_HEIGHT * scale))

    img_small = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    if random.random() > 0.5:
        img_small = img_small.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 2.0)))
    return img_small.resize((PLATE_WIDTH, PLATE_HEIGHT), Image.Resampling.LANCZOS)


def add_weather_fog(img: Image.Image, intensity: tuple[float, float] = (0.1, 0.5)) -> Image.Image:
    array = np.array(img).astype(np.float32)
    alpha = random.uniform(intensity[0], intensity[1])

    fog_color = np.array(
        [random.randint(200, 255), random.randint(200, 255), random.randint(200, 255)],
        dtype=np.float32,
    )
    fog_array = np.ones_like(array) * fog_color
    array = array * (1.0 - alpha) + fog_array * alpha
    return Image.fromarray(clamp_uint8(array))


def add_rain_streaks(img: Image.Image, num_streaks: int = 30) -> Image.Image:
    array = np.array(img).copy()
    height, width = array.shape[:2]

    if CV2_AVAILABLE:
        for _ in range(random.randint(5, num_streaks)):
            start_x = random.randint(0, width - 1)
            start_y = random.randint(0, height - 1)
            length = random.randint(10, 30)
            angle = random.uniform(70, 110)
            delta_x = int(length * math.cos(math.radians(angle)))
            delta_y = int(length * math.sin(math.radians(angle)))
            color = (200, 220, 255)
            cv2.line(
                array,
                (start_x, start_y),
                (max(0, min(width - 1, start_x + delta_x)), max(0, min(height - 1, start_y + delta_y))),
                color,
                random.randint(1, 2),
            )
        return Image.fromarray(array)

    pil_image = Image.fromarray(array)
    draw = ImageDraw.Draw(pil_image)
    for _ in range(random.randint(5, num_streaks)):
        start_x = random.randint(0, width - 1)
        start_y = random.randint(0, height - 1)
        length = random.randint(10, 30)
        draw.line(
            (start_x, start_y, start_x + random.randint(-4, 4), min(height - 1, start_y + length)),
            fill=(200, 220, 255),
            width=random.randint(1, 2),
        )
    return pil_image


def add_occlusion(img: Image.Image, prob: float = 0.3) -> Image.Image:
    if random.random() > prob:
        return img

    array = np.array(img).copy()
    height, width = array.shape[:2]
    occlusion_type = random.choice(["dirt", "shadow", "patch"])

    if CV2_AVAILABLE:
        if occlusion_type == "dirt":
            for _ in range(random.randint(3, 10)):
                center_x = random.randint(0, width - 1)
                center_y = random.randint(0, height - 1)
                radius = random.randint(5, 20)
                color = (random.randint(0, 80), random.randint(0, 80), random.randint(0, 80))
                cv2.circle(array, (center_x, center_y), radius, color, -1)
        elif occlusion_type == "shadow":
            alpha = random.uniform(0.2, 0.6)
            x1 = random.randint(0, max(1, width // 2))
            y1 = random.randint(0, max(1, height // 2))
            x2 = random.randint(min(width - 1, x1 + 40), width - 1)
            y2 = random.randint(min(height - 1, y1 + 40), height - 1)

            overlay = array.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), -1)
            cv2.addWeighted(overlay, alpha, array, 1 - alpha, 0, array)
        else:
            x1 = random.randint(0, max(0, width - 30))
            y1 = random.randint(0, max(0, height - 30))
            x2 = min(width - 1, x1 + random.randint(20, 50))
            y2 = min(height - 1, y1 + random.randint(20, 50))
            color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
            cv2.rectangle(array, (x1, y1), (x2, y2), color, -1)
        return Image.fromarray(array)

    pil_image = Image.fromarray(array)
    draw = ImageDraw.Draw(pil_image)

    if occlusion_type == "dirt":
        for _ in range(random.randint(3, 10)):
            center_x = random.randint(0, width - 1)
            center_y = random.randint(0, height - 1)
            radius = random.randint(5, 20)
            color = (random.randint(0, 80), random.randint(0, 80), random.randint(0, 80))
            draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=color)
    elif occlusion_type == "shadow":
        x1 = random.randint(0, max(1, width // 2))
        y1 = random.randint(0, max(1, height // 2))
        x2 = random.randint(min(width - 1, x1 + 40), width - 1)
        y2 = random.randint(min(height - 1, y1 + 40), height - 1)
        shadow = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        alpha = int(random.uniform(60, 150))
        shadow_draw.rectangle((x1, y1, x2, y2), fill=(0, 0, 0, alpha))
        pil_image = Image.alpha_composite(pil_image.convert("RGBA"), shadow).convert("RGB")
    else:
        x1 = random.randint(0, max(0, width - 30))
        y1 = random.randint(0, max(0, height - 30))
        x2 = min(width - 1, x1 + random.randint(20, 50))
        y2 = min(height - 1, y1 + random.randint(20, 50))
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
        draw.rectangle((x1, y1, x2, y2), fill=color)

    return pil_image


def add_glare(img: Image.Image, prob: float = 0.2) -> Image.Image:
    if random.random() > prob:
        return img

    array = np.array(img).astype(np.float32)
    height, width = array.shape[:2]

    center_x = random.randint(0, width - 1)
    center_y = random.randint(0, height - 1)
    radius = random.randint(20, 60)
    intensity = random.randint(150, 255)

    yy, xx = np.mgrid[0:height, 0:width]
    distance = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
    mask = np.clip(1.0 - (distance / radius), 0.0, 1.0)
    array += mask[:, :, None] * intensity

    return Image.fromarray(clamp_uint8(array))


def add_contrast_adjust(img: Image.Image, low: float = 0.7, high: float = 1.3) -> Image.Image:
    factor = random.uniform(low, high)
    img = ImageOps.autocontrast(img, cutoff=0)

    array = np.array(img).astype(np.float32)
    mean = array.mean(axis=(0, 1), keepdims=True)
    array = (array - mean) * factor + mean
    return Image.fromarray(clamp_uint8(array))


def generate_non_tribal_plate() -> tuple[Image.Image, dict[str, Any]]:
    img = Image.new("RGB", (PLATE_WIDTH, PLATE_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    template_name, template_fn = random.choice(NON_TRIBAL_TEMPLATES)
    template_fn(draw, PLATE_WIDTH, PLATE_HEIGHT)

    visible_text = random_plate_number()
    font_number = safe_font(72)
    center_text(draw, (PLATE_WIDTH // 2, PLATE_HEIGHT // 2 + 30), visible_text, font_number, (0, 0, 0))

    metadata = {
        "plate_category": "non_tribal",
        "tribe": "",
        "template": template_name,
        "visible_text": visible_text,
        "plate_text": normalize_ocr_label(visible_text),
    }
    return img, metadata


def generate_tribal_plate(tribe_name: str | None = None) -> tuple[Image.Image, dict[str, Any]]:
    img = Image.new("RGB", (PLATE_WIDTH, PLATE_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    tribe = random.choice(TRIBAL_NATIONS) if tribe_name is None else next(item for item in TRIBAL_NATIONS if item["name"] == tribe_name)
    template_fn = TRIBAL_TEMPLATES.get(tribe["name"], draw_tribal_generic)
    visible_text = template_fn(draw, PLATE_WIDTH, PLATE_HEIGHT, tribe)

    metadata = {
        "plate_category": "tribal",
        "tribe": tribe["name"],
        "template": tribe["name"].lower(),
        "visible_text": visible_text,
        "plate_text": normalize_ocr_label(visible_text),
    }
    return img, metadata


def apply_degradation_pipeline(img: Image.Image) -> tuple[Image.Image, dict[str, bool]]:
    applied = {
        "distance": False,
        "motion_blur": False,
        "fog": False,
        "rain": False,
        "occlusion": False,
        "glare": False,
        "low_light": False,
        "contrast_adjust": False,
    }

    if random.random() > 0.5:
        img = add_distance_effect(img, min_scale=0.4, max_scale=0.9)
        applied["distance"] = True

    if random.random() > 0.6:
        img = add_motion_blur(img)
        applied["motion_blur"] = True

    if random.random() > 0.4:
        img = add_weather_fog(img, intensity=(0.1, 0.4))
        applied["fog"] = True

    if random.random() > 0.7:
        img = add_rain_streaks(img)
        applied["rain"] = True

    if random.random() > 0.5:
        img = add_occlusion(img, prob=0.8)
        applied["occlusion"] = True

    if random.random() > 0.6:
        img = add_glare(img)
        applied["glare"] = True

    if random.random() > 0.5:
        img = add_low_light(img, brightness_factor=(0.2, 0.8), color_temp_shift=True, add_noise=True)
        applied["low_light"] = True
    else:
        img = add_contrast_adjust(img, low=0.8, high=1.2)
        applied["contrast_adjust"] = True
        if random.random() > 0.7:
            img = add_low_light(img, brightness_factor=(0.6, 1.0), color_temp_shift=False, add_noise=True)
            applied["low_light"] = True

    return img, applied


def generate_plate_sample(tribal_ratio: float, apply_degradation: bool) -> tuple[Image.Image, dict[str, Any]]:
    if random.random() < tribal_ratio:
        img, metadata = generate_tribal_plate()
    else:
        img, metadata = generate_non_tribal_plate()

    if apply_degradation:
        img, effects = apply_degradation_pipeline(img)
        metadata["degraded"] = True
        metadata.update({f"fx_{key}": value for key, value in effects.items()})
    else:
        metadata["degraded"] = False
        metadata.update(
            {
                "fx_distance": False,
                "fx_motion_blur": False,
                "fx_fog": False,
                "fx_rain": False,
                "fx_occlusion": False,
                "fx_glare": False,
                "fx_low_light": False,
                "fx_contrast_adjust": False,
            }
        )
    return img, metadata


def allocate_split_counts(count: int, ratios: tuple[float, float, float]) -> list[SplitPlan]:
    raw_counts = [count * ratio for ratio in ratios]
    counts = [math.floor(value) for value in raw_counts]
    remainder = count - sum(counts)
    fractional_order = sorted(
        range(len(raw_counts)),
        key=lambda index: (raw_counts[index] - counts[index]),
        reverse=True,
    )
    for index in fractional_order[:remainder]:
        counts[index] += 1
    return [SplitPlan(split_name=name, sample_count=sample_count) for name, sample_count in zip(SPLIT_NAMES, counts, strict=True)]


def write_split_labels(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        path.write_text("image_file,plate_text\n", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_metadata_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_metadata_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def build_manifest(
    *,
    output_root: Path,
    dataset_name: str,
    dataset_version: str,
    split_plan: list[SplitPlan],
    approved: bool,
    reviewer: str | None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "task": "plate_ocr",
        "format": "ocr_manifest",
        "storage_root": output_root.as_posix(),
        "review_status": "approved" if approved else "pending",
        "provenance": {
            "source_name": "reposcan-oklahoma-synthetic-ocr-generator",
            "source_kind": "synthetic",
            "license_tier": "internal",
            "license_name": "internal generated synthetic support data",
            "license_reference": "internal://reposcan/synthetic-oklahoma-ocr-generator",
            "region": "us-ok",
            "notes": "Synthetic Oklahoma plate crops for OCR support only. Labels are normalized to the active RepoScan alphanumeric OCR dictionary.",
        },
        "splits": [
            {
                "split": split.split_name,
                "relative_path": f"{split.split_name}/images",
                "label_path": f"{split.split_name}/labels.csv",
                "sample_count": split.sample_count,
                "tags": ["synthetic", "oklahoma", "ocr_support"],
            }
            for split in split_plan
        ],
        "notes": "Use as supplemental OCR support data, not as a replacement for reviewed field captures.",
    }
    if approved:
        manifest["annotation_review"] = {
            "reviewer": reviewer,
            "reviewed_at_utc": utc_now_utc(),
            "accepted_tasks": ["plate_ocr"],
            "notes": "Approved synthetic OCR support dataset for controlled training use.",
        }
    return manifest


def write_dataset_readme(
    *,
    path: Path,
    dataset_name: str,
    dataset_version: str,
    sample_count: int,
    output_root: Path,
    manifest_path: Path,
    apply_degradation: bool,
    tribal_ratio: float,
) -> None:
    path.write_text(
        "\n".join(
            [
                f"RepoScan Pro synthetic OCR dataset: {dataset_name}",
                "",
                f"dataset_version: {dataset_version}",
                f"total_images: {sample_count}",
                f"output_root: {output_root}",
                f"manifest: {manifest_path}",
                f"opencv_available: {CV2_AVAILABLE}",
                f"degradation_enabled: {apply_degradation}",
                f"tribal_ratio: {tribal_ratio}",
                "",
                "Layout:",
                "- train/images + train/labels.csv",
                "- validation/images + validation/labels.csv",
                "- holdout/images + holdout/labels.csv",
                "- metadata.csv",
                "- metadata.jsonl",
                "",
                "Integration:",
                "- Validate the manifest with scripts/validate_training_dataset_manifest.py",
                "- Prepare OCR workflow with scripts/train_ocr_recognizer.py",
                "- Keep this dataset supplemental to reviewed field plate crops",
                "",
                "Label policy:",
                "- visible_text preserves the rendered registration string",
                "- plate_text is normalized to uppercase alphanumeric characters for the current RepoScan OCR dictionary",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def resolve_output_path(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a RepoScan-compatible synthetic Oklahoma OCR dataset without touching runtime paths."
    )
    parser.add_argument("--count", type=int, default=400, help="Total number of images to generate.")
    parser.add_argument(
        "--output-root",
        default=f"data/staged/synthetic_oklahoma_ocr_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        help="Output dataset directory.",
    )
    parser.add_argument("--dataset-name", help="Dataset manifest name. Defaults to the output directory name.")
    parser.add_argument(
        "--dataset-version",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Dataset version string for the manifest.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Training split ratio.")
    parser.add_argument("--validation-ratio", type=float, default=0.1, help="Validation split ratio.")
    parser.add_argument("--holdout-ratio", type=float, default=0.1, help="Holdout split ratio.")
    parser.add_argument("--tribal-ratio", type=float, default=0.5, help="Ratio of tribal plates from 0.0 to 1.0.")
    parser.add_argument("--no-degradation", action="store_true", help="Disable degradation effects.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--image-format", choices=["jpg", "png"], default="png", help="Image output format.")
    parser.add_argument("--jpg-quality", type=int, default=95, help="JPEG quality when using JPG.")
    parser.add_argument(
        "--manifest-output",
        help="Optional manifest output path. Defaults to <output-root>/manifest.yaml.",
    )
    parser.add_argument("--approve", action="store_true", help="Write the generated manifest as approved.")
    parser.add_argument("--reviewer", help="Reviewer id required when --approve is used.")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.count <= 0:
        raise ValueError("--count must be greater than 0")
    if not 0.0 <= args.tribal_ratio <= 1.0:
        raise ValueError("--tribal-ratio must be between 0.0 and 1.0")
    if not 1 <= args.jpg_quality <= 100:
        raise ValueError("--jpg-quality must be between 1 and 100")
    ratios = args.train_ratio + args.validation_ratio + args.holdout_ratio
    if ratios <= 0:
        raise ValueError("split ratios must add up to more than 0")
    if not math.isclose(ratios, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("--train-ratio, --validation-ratio, and --holdout-ratio must add up to 1.0")
    if args.approve and not args.reviewer:
        raise ValueError("--reviewer is required when --approve is used")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    repo_root = Path(__file__).resolve().parents[1]
    output_root = resolve_output_path(repo_root, args.output_root)
    manifest_path = (
        resolve_output_path(repo_root, args.manifest_output)
        if args.manifest_output
        else output_root / "manifest.yaml"
    )
    dataset_name = args.dataset_name or output_root.name

    random.seed(args.seed)
    np.random.seed(args.seed)

    split_plan = allocate_split_counts(
        args.count,
        (args.train_ratio, args.validation_ratio, args.holdout_ratio),
    )

    ensure_dir(output_root)
    split_label_rows: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLIT_NAMES}
    metadata_rows: list[dict[str, Any]] = []
    extension = args.image_format.lower()

    print("=" * 72)
    print("RepoScan Pro Synthetic Oklahoma OCR Dataset Generator")
    print("=" * 72)
    print(f"Output root       : {output_root}")
    print(f"Manifest path     : {manifest_path}")
    print(f"Dataset name      : {dataset_name}")
    print(f"Dataset version   : {args.dataset_version}")
    print(f"Total count       : {args.count}")
    print(f"Tribal ratio      : {args.tribal_ratio}")
    print(f"Degradation       : {'disabled' if args.no_degradation else 'enabled'}")
    print(f"OpenCV available  : {CV2_AVAILABLE}")
    print(f"Seed              : {args.seed}")
    print("=" * 72)

    for split in split_plan:
        image_dir = output_root / split.split_name / "images"
        ensure_dir(image_dir)

        for index in range(split.sample_count):
            image, metadata = generate_plate_sample(
                tribal_ratio=args.tribal_ratio,
                apply_degradation=not args.no_degradation,
            )
            filename = f"{split.split_name}_{index:05d}.{extension}"
            image_path = image_dir / filename

            if extension == "jpg":
                image.save(image_path, quality=args.jpg_quality)
            else:
                image.save(image_path)

            label_row = {
                "image_file": filename,
                "plate_text": metadata["plate_text"],
                "visible_text": metadata["visible_text"],
                "plate_category": metadata["plate_category"],
                "tribe": metadata["tribe"],
                "template": metadata["template"],
                "degraded": metadata["degraded"],
            }
            for key, value in metadata.items():
                if key.startswith("fx_"):
                    label_row[key] = value

            metadata_row = {
                "split": split.split_name,
                "filename": f"{split.split_name}/images/{filename}",
                **metadata,
            }
            split_label_rows[split.split_name].append(label_row)
            metadata_rows.append(metadata_row)

        label_path = output_root / split.split_name / "labels.csv"
        write_split_labels(label_path, split_label_rows[split.split_name])
        print(f"{split.split_name.title():<16}: {split.sample_count}")

    manifest = build_manifest(
        output_root=output_root,
        dataset_name=dataset_name,
        dataset_version=args.dataset_version,
        split_plan=split_plan,
        approved=args.approve,
        reviewer=args.reviewer,
    )
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    write_metadata_csv(output_root / "metadata.csv", metadata_rows)
    write_metadata_jsonl(output_root / "metadata.jsonl", metadata_rows)
    write_dataset_readme(
        path=output_root / "README.txt",
        dataset_name=dataset_name,
        dataset_version=args.dataset_version,
        sample_count=args.count,
        output_root=output_root,
        manifest_path=manifest_path,
        apply_degradation=not args.no_degradation,
        tribal_ratio=args.tribal_ratio,
    )

    print("=" * 72)
    print(f"Done. Dataset saved to : {output_root}")
    print(f"Manifest               : {manifest_path}")
    print(f"Metadata CSV           : {output_root / 'metadata.csv'}")
    print(f"Metadata JSONL         : {output_root / 'metadata.jsonl'}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
