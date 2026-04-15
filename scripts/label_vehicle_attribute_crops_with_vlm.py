from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any, Protocol


DEFAULT_QWEN_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"

COLOR_LABELS = {"black", "white", "silver", "gray", "red", "blue", "green", "yellow", "orange", "brown", "other"}
BODY_TYPE_LABELS = {
    "sedan",
    "coupe",
    "hatchback",
    "wagon",
    "suv",
    "crossover",
    "pickup",
    "van",
    "minivan",
    "box_truck",
    "bus",
    "motorcycle",
    "unknown",
}

VLM_FIELDNAMES = [
    "suggested_vlm_provider",
    "suggested_vlm_model_name",
    "suggested_vlm_contains_usable_vehicle",
    "suggested_vlm_vehicle_make",
    "suggested_vlm_vehicle_model",
    "suggested_vlm_vehicle_model_family",
    "suggested_vlm_vehicle_year",
    "suggested_vlm_vehicle_year_range",
    "suggested_vlm_vehicle_trim",
    "suggested_vlm_vehicle_color",
    "suggested_vlm_body_type",
    "suggested_vlm_confidence",
    "suggested_vlm_evidence",
    "suggested_vlm_review_action",
    "suggested_vlm_raw_response",
    "vlm_label_error",
]

REVIEW_FIELDNAMES = [
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
    parser = argparse.ArgumentParser(
        description="Use pretrained VLMs to add conservative vehicle attribute suggestions to RepoScan crop review CSVs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    label = subparsers.add_parser("label-crops", help="Add VLM suggestion columns to a crop review CSV.")
    label.add_argument("--review-csv", required=True)
    label.add_argument("--output-csv", required=True)
    label.add_argument("--provider", choices=["openai", "qwen2_5_vl", "fixture"], default="qwen2_5_vl")
    label.add_argument("--model", help="Provider model name. Defaults to the provider's recommended baseline.")
    label.add_argument("--fixture-jsonl", help="JSONL fixture for deterministic tests or offline dry runs.")
    label.add_argument("--limit", type=int)
    label.add_argument("--skip-existing", action="store_true", help="Skip rows that already have VLM suggestions.")
    label.add_argument("--overwrite", action="store_true")
    label.add_argument("--progress-every", type=int, default=25)
    label.add_argument("--max-new-tokens", type=int, default=360)
    label.add_argument("--device-map", default="auto", help="Transformers device_map for Qwen2.5-VL.")
    label.add_argument("--temperature", type=float, default=0.0)
    label.add_argument("--openai-api-key-env", default="OPENAI_API_KEY")

    consensus = subparsers.add_parser(
        "apply-consensus",
        help="Fill RepoScan review fields from high-confidence VLM consensus while keeping rows pending by default.",
    )
    consensus.add_argument("--input-csv", required=True)
    consensus.add_argument("--output-csv", required=True)
    consensus.add_argument(
        "--task",
        choices=["vehicle_make_model_classification", "vehicle_color_classification", "vehicle_year_classification"],
        required=True,
    )
    consensus.add_argument("--min-vlm-confidence", type=float, default=0.75)
    consensus.add_argument("--min-color-confidence", type=float, default=0.70)
    consensus.add_argument("--min-onnx-confidence", type=float, default=0.75)
    consensus.add_argument("--min-year-confidence", type=float, default=0.90)
    consensus.add_argument("--allow-year-range", action="store_true")
    consensus.add_argument("--allow-vlm-overrides-onnx", action="store_true")
    consensus.add_argument("--mark-reviewed", action="store_true")
    consensus.add_argument("--overwrite", action="store_true")

    return parser.parse_args()


def _vehicle_attribute_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "contains_usable_vehicle",
            "make",
            "model",
            "model_family",
            "year",
            "year_range",
            "trim",
            "color",
            "body_type",
            "confidence",
            "evidence",
            "review_action",
        ],
        "properties": {
            "contains_usable_vehicle": {"type": "boolean"},
            "make": {"type": ["string", "null"]},
            "model": {"type": ["string", "null"]},
            "model_family": {"type": ["string", "null"]},
            "year": {"type": ["integer", "string", "null"]},
            "year_range": {"type": ["string", "null"]},
            "trim": {"type": ["string", "null"]},
            "color": {"type": ["string", "null"], "enum": sorted(COLOR_LABELS) + [None]},
            "body_type": {"type": ["string", "null"], "enum": sorted(BODY_TYPE_LABELS) + [None]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "evidence": {"type": "string"},
            "review_action": {
                "type": "string",
                "enum": ["accept_suggestion", "needs_human_review", "reject_crop"],
            },
        },
    }


def _prompt_for_row(row: dict[str, str]) -> str:
    source_label = row.get("source_label", "").strip() or "unknown"
    return (
        "You are labeling vehicle crops for a RepoScan Pro training dataset focused on Oklahoma road vehicles. "
        "Inspect only the visible vehicle in the crop. Be conservative: if make, model, trim, or exact year cannot be "
        "visually supported, return null for that field and set review_action to needs_human_review. "
        "Use model_family for broad families such as f_series, silverado, ram_pickup, camry, accord, civic, altima, "
        "tahoe, suburban, explorer, escape, rav4, cr_v, corolla, malibu, charger, challenger, sierra, or unknown. "
        "Exact year should only be filled when visible design cues strongly support it; otherwise use year_range or null. "
        "Color should be the dominant exterior body color, not window tint, reflections, wheels, or background. "
        f"The source detection class was {source_label}. Return only one JSON object matching the required schema."
    )


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = [character if character.isalnum() else "_" for character in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "none", "null", "unknown", "n/a", "not visible", "uncertain"}:
        return ""
    return text


def _clean_slug_text(value: Any) -> str:
    return _slugify(_clean_text(value))


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "usable"}:
        return True
    if text in {"0", "false", "no", "n", "unusable"}:
        return False
    return None


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _coerce_year(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        value = int(value)
    text = str(value).strip()
    match = re.fullmatch(r"(19|20)\d{2}", text)
    return match.group(0) if match else ""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("VLM response was not a JSON object")
    return parsed


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


def _ensure_fieldnames(fieldnames: list[str], extra_fields: list[str]) -> list[str]:
    output = list(fieldnames)
    for field_name in extra_fields:
        if field_name not in output:
            output.append(field_name)
    return output


def _resolve_crop_path(value: str, *, csv_path: Path) -> Path:
    crop_path = Path(value)
    if crop_path.is_absolute():
        return crop_path
    return (csv_path.parent / crop_path).resolve()


class VehicleAttributeLabeler(Protocol):
    provider: str
    model_name: str

    def label(self, crop_path: Path, row: dict[str, str]) -> dict[str, Any]:
        ...


class FixtureLabeler:
    provider = "fixture"

    def __init__(self, fixture_jsonl: Path):
        self.model_name = str(fixture_jsonl)
        self.records: dict[str, dict[str, Any]] = {}
        with fixture_jsonl.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                key = str(record.get("crop_id") or record.get("crop_filepath") or "").strip()
                if not key:
                    raise ValueError("fixture JSONL records must include crop_id or crop_filepath")
                response = record.get("response", record)
                self.records[key] = response

    def label(self, crop_path: Path, row: dict[str, str]) -> dict[str, Any]:
        key = str(row.get("crop_id") or "").strip()
        if key in self.records:
            return dict(self.records[key])
        path_key = str(row.get("crop_filepath") or "").strip()
        if path_key in self.records:
            return dict(self.records[path_key])
        if str(crop_path) in self.records:
            return dict(self.records[str(crop_path)])
        raise KeyError(f"no fixture label for crop_id={key!r}")


class OpenAIVehicleLabeler:
    provider = "openai"

    def __init__(self, *, model_name: str, api_key_env: str, temperature: float):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the OpenAI optional dependency with `python -m pip install openai`.") from exc
        self.model_name = model_name
        self.temperature = temperature
        api_key = os.environ.get(api_key_env) if api_key_env else None
        self.client = OpenAI(api_key=api_key) if api_key else OpenAI()

    def label(self, crop_path: Path, row: dict[str, str]) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(crop_path.name)[0] or "image/jpeg"
        image_bytes = crop_path.read_bytes()
        image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": _prompt_for_row(row)},
                        {"type": "input_image", "image_url": image_url, "detail": "high"},
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "reposcan_vehicle_attribute_label",
                    "schema": _vehicle_attribute_schema(),
                    "strict": True,
                }
            },
            temperature=self.temperature,
        )
        output_text = getattr(response, "output_text", None)
        if output_text is None:
            output_text = response.model_dump_json()
        return _extract_json_object(str(output_text))


class QwenVehicleLabeler:
    provider = "qwen2_5_vl"

    def __init__(self, *, model_name: str, device_map: str, max_new_tokens: int):
        try:
            import torch
            from qwen_vl_utils import process_vision_info
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        except ImportError as exc:
            raise RuntimeError(
                "Install Qwen VLM dependencies in a GPU runtime with "
                "`python -m pip install transformers accelerate qwen-vl-utils` and a matching torch build."
            ) from exc
        self.torch = torch
        self.process_vision_info = process_vision_info
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map=device_map,
        )
        self.processor = AutoProcessor.from_pretrained(model_name)

    def label(self, crop_path: Path, row: dict[str, str]) -> dict[str, Any]:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(crop_path)},
                    {"type": "text", "text": _prompt_for_row(row)},
                ],
            }
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = self.process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        model_device = getattr(self.model, "device", None)
        if model_device is not None and str(model_device) != "meta":
            inputs = inputs.to(model_device)
        with self.torch.inference_mode():
            generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        generated_ids_trimmed = [
            output_ids[len(input_ids) :] for input_ids, output_ids in zip(inputs.input_ids, generated_ids, strict=False)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        return _extract_json_object(output_text)


def _build_labeler(args: argparse.Namespace) -> VehicleAttributeLabeler:
    if args.provider == "fixture":
        if not args.fixture_jsonl:
            raise ValueError("--fixture-jsonl is required when --provider fixture is used")
        return FixtureLabeler(Path(args.fixture_jsonl).resolve())
    if args.provider == "openai":
        return OpenAIVehicleLabeler(
            model_name=args.model or DEFAULT_OPENAI_MODEL,
            api_key_env=args.openai_api_key_env,
            temperature=args.temperature,
        )
    if args.provider == "qwen2_5_vl":
        return QwenVehicleLabeler(
            model_name=args.model or DEFAULT_QWEN_MODEL,
            device_map=args.device_map,
            max_new_tokens=args.max_new_tokens,
        )
    raise ValueError(f"unsupported provider: {args.provider}")


def _normalize_label_response(response: dict[str, Any]) -> dict[str, str]:
    usable = _coerce_bool(response.get("contains_usable_vehicle"))
    color = _clean_slug_text(response.get("color"))
    if color not in COLOR_LABELS:
        color = ""
    body_type = _clean_slug_text(response.get("body_type")) or "unknown"
    if body_type not in BODY_TYPE_LABELS:
        body_type = "unknown"
    confidence = _coerce_float(response.get("confidence"))
    review_action = _clean_slug_text(response.get("review_action")) or "needs_human_review"
    if review_action not in {"accept_suggestion", "needs_human_review", "reject_crop"}:
        review_action = "needs_human_review"
    return {
        "suggested_vlm_contains_usable_vehicle": "" if usable is None else str(usable).lower(),
        "suggested_vlm_vehicle_make": _clean_slug_text(response.get("make")),
        "suggested_vlm_vehicle_model": _clean_slug_text(response.get("model")),
        "suggested_vlm_vehicle_model_family": _clean_slug_text(response.get("model_family")),
        "suggested_vlm_vehicle_year": _coerce_year(response.get("year")),
        "suggested_vlm_vehicle_year_range": _clean_text(response.get("year_range")),
        "suggested_vlm_vehicle_trim": _clean_slug_text(response.get("trim")),
        "suggested_vlm_vehicle_color": color,
        "suggested_vlm_body_type": body_type,
        "suggested_vlm_confidence": f"{confidence:.4f}",
        "suggested_vlm_evidence": _clean_text(response.get("evidence")),
        "suggested_vlm_review_action": review_action,
        "suggested_vlm_raw_response": json.dumps(response, ensure_ascii=True, sort_keys=True),
        "vlm_label_error": "",
    }


def label_crops(args: argparse.Namespace) -> int:
    review_csv = Path(args.review_csv).resolve()
    output_csv = Path(args.output_csv).resolve()
    if output_csv.exists() and not args.overwrite:
        raise FileExistsError(f"output CSV already exists: {output_csv}. Pass --overwrite to replace it.")

    rows, fieldnames = _read_csv(review_csv)
    fieldnames = _ensure_fieldnames(fieldnames, VLM_FIELDNAMES)
    labeler = _build_labeler(args)

    processed = 0
    errors = 0
    skipped = 0
    for row in rows:
        if args.skip_existing and row.get("suggested_vlm_provider") and not row.get("vlm_label_error"):
            skipped += 1
            continue
        if args.limit is not None and processed >= args.limit:
            continue

        crop_path = _resolve_crop_path(str(row.get("crop_filepath") or ""), csv_path=review_csv)
        row["suggested_vlm_provider"] = labeler.provider
        row["suggested_vlm_model_name"] = labeler.model_name
        if not crop_path.exists():
            row["vlm_label_error"] = f"missing crop file: {crop_path}"
            errors += 1
            processed += 1
            continue
        try:
            response = labeler.label(crop_path, row)
            row.update(_normalize_label_response(response))
        except Exception as exc:
            row["vlm_label_error"] = str(exc)
            errors += 1
        processed += 1
        if args.progress_every > 0 and processed % args.progress_every == 0:
            print(f"VLM-labeled {processed} crop row(s)")

    _write_csv(output_csv, rows, fieldnames)
    print(f"Wrote VLM suggestions: {output_csv}")
    print(json.dumps({"rows": len(rows), "processed": processed, "skipped": skipped, "errors": errors}, indent=2))
    return 0 if errors == 0 else 1


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


def _onnx_suggestion_conflicts(row: dict[str, str], *, args: argparse.Namespace, make: str, model: str) -> bool:
    if args.allow_vlm_overrides_onnx:
        return False
    onnx_confidence = _coerce_float(row.get("suggested_make_model_top1_confidence"), default=0.0)
    if onnx_confidence < args.min_onnx_confidence:
        return False
    onnx_make = _clean_slug_text(row.get("suggested_vehicle_make"))
    onnx_model = _clean_slug_text(row.get("suggested_vehicle_model"))
    return bool((onnx_make and onnx_make != make) or (onnx_model and onnx_model != model))


def _apply_consensus_to_row(row: dict[str, str], *, args: argparse.Namespace) -> str:
    usable = _coerce_bool(row.get("suggested_vlm_contains_usable_vehicle"))
    confidence = _coerce_float(row.get("suggested_vlm_confidence"), default=0.0)
    review_action = _clean_slug_text(row.get("suggested_vlm_review_action"))
    if usable is False or review_action == "reject_crop":
        row["reposcan_accepted"] = "false"
        row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), "vlm_rejected_unusable_crop")
        return "rejected"
    if usable is not True or confidence < args.min_vlm_confidence:
        row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), "vlm_consensus_below_threshold")
        return "skipped"

    applied = False
    make = _clean_slug_text(row.get("suggested_vlm_vehicle_make"))
    model = _clean_slug_text(row.get("suggested_vlm_vehicle_model_family")) or _clean_slug_text(
        row.get("suggested_vlm_vehicle_model")
    )
    color = _clean_slug_text(row.get("suggested_vlm_vehicle_color"))
    year = _coerce_year(row.get("suggested_vlm_vehicle_year"))
    year_range = _clean_text(row.get("suggested_vlm_vehicle_year_range"))

    if args.task == "vehicle_color_classification":
        heuristic_color = _clean_slug_text(row.get("suggested_vehicle_color"))
        heuristic_confidence = _coerce_float(row.get("suggested_vehicle_color_confidence"), default=0.0)
        if (
            heuristic_color
            and heuristic_confidence >= args.min_color_confidence
            and color
            and heuristic_color != color
        ):
            row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), "color_consensus_conflict")
            return "skipped"
        if color in COLOR_LABELS:
            row["reposcan_vehicle_color"] = color
            applied = True

    if args.task == "vehicle_make_model_classification":
        if make and model and not _onnx_suggestion_conflicts(row, args=args, make=make, model=model):
            row["reposcan_vehicle_make"] = make
            row["reposcan_vehicle_model"] = model
            row["reposcan_class_label"] = _slugify(f"{make}_{model}")
            applied = True
        else:
            row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), "make_model_consensus_conflict")
            return "skipped"

    if args.task == "vehicle_year_classification":
        if year and confidence >= args.min_year_confidence:
            row["reposcan_vehicle_year"] = year
            applied = True
        elif args.allow_year_range and year_range:
            row["reposcan_vehicle_year"] = _slugify(year_range)
            applied = True
        else:
            row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), "year_consensus_too_uncertain")
            return "skipped"

    if not applied:
        return "skipped"

    body_type = _clean_slug_text(row.get("suggested_vlm_body_type"))
    provider = _clean_slug_text(row.get("suggested_vlm_provider")) or "vlm"
    row["reposcan_accepted"] = "true"
    if args.mark_reviewed:
        row["reposcan_reviewed"] = "true"
        row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), f"ai_assisted_consensus_reviewed:{provider}")
    else:
        row["reposcan_reviewed"] = row.get("reposcan_reviewed") or "false"
        row["reviewer_notes"] = _append_note(row.get("reviewer_notes", ""), f"ai_assisted_consensus_pending_review:{provider}")
    row["reposcan_oklahoma_tags"] = _append_pipe_value(row.get("reposcan_oklahoma_tags", ""), f"ai_assisted:{provider}")
    if body_type and body_type != "unknown":
        row["reposcan_oklahoma_tags"] = _append_pipe_value(row.get("reposcan_oklahoma_tags", ""), f"vehicle_class:{body_type}")
    if make and model:
        row["reposcan_oklahoma_tags"] = _append_pipe_value(
            row.get("reposcan_oklahoma_tags", ""), f"make_model:{_slugify(f'{make}_{model}')}"
        )
    return "applied"


def apply_consensus(args: argparse.Namespace) -> int:
    input_csv = Path(args.input_csv).resolve()
    output_csv = Path(args.output_csv).resolve()
    if output_csv.exists() and not args.overwrite:
        raise FileExistsError(f"output CSV already exists: {output_csv}. Pass --overwrite to replace it.")

    rows, fieldnames = _read_csv(input_csv)
    fieldnames = _ensure_fieldnames(fieldnames, REVIEW_FIELDNAMES)

    counts = {"applied": 0, "skipped": 0, "rejected": 0}
    for row in rows:
        status = _apply_consensus_to_row(row, args=args)
        counts[status] = counts.get(status, 0) + 1

    _write_csv(output_csv, rows, fieldnames)
    print(f"Wrote consensus CSV: {output_csv}")
    print(json.dumps({"rows": len(rows), **counts}, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "label-crops":
        return label_crops(args)
    if args.command == "apply-consensus":
        return apply_consensus(args)
    raise ValueError(f"unknown command: {args.command}")


def _entrypoint() -> int:
    try:
        return main()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
