from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from reposcan_contracts.config.loader import load_training_dataset_manifest
from reposcan_contracts.dataset import DatasetFormat

from .service import PreprocessingService


@dataclass(frozen=True)
class OcrBenchmarkInputRecord:
    image_key: str
    image_path: Path
    expected_text: str
    low_light: bool | None = None


@dataclass(frozen=True)
class StagedOcrBenchmarkRecord:
    image_key: str
    expected_text: str
    raw_image_path: Path
    preprocessed_image_path: Path
    low_light: bool
    low_light_source: str
    preprocessing: dict


def normalize_ocr_text(text: str | None) -> str:
    if not text:
        return ""
    return "".join(character for character in text.upper() if character.isalnum())


def _levenshtein_distance(expected: str, actual: str) -> int:
    if expected == actual:
        return 0
    if not expected:
        return len(actual)
    if not actual:
        return len(expected)

    previous = list(range(len(actual) + 1))
    for i, expected_char in enumerate(expected, start=1):
        current = [i]
        for j, actual_char in enumerate(actual, start=1):
            cost = 0 if expected_char == actual_char else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def character_accuracy(expected: str, actual: str | None) -> float:
    normalized_expected = normalize_ocr_text(expected)
    normalized_actual = normalize_ocr_text(actual)
    denominator = max(len(normalized_expected), len(normalized_actual), 1)
    distance = _levenshtein_distance(normalized_expected, normalized_actual)
    return max(0.0, 1.0 - (distance / denominator))


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_storage_root(repo_root: Path, storage_root: str) -> Path:
    root = Path(storage_root)
    if root.is_absolute():
        return root.resolve()
    return (repo_root / root).resolve()


def _resolve_image_path(storage_root: Path, split_relative_path: str, image_key: str) -> Path:
    image_path = Path(image_key)
    if image_path.is_absolute():
        return image_path.resolve()

    candidates = [
        storage_root / image_path,
        storage_root / split_relative_path / image_path,
        storage_root / split_relative_path / image_path.name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[-1].resolve()


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def load_low_light_metadata(
    metadata_csv_path: Path,
    *,
    split_name: str,
    filename_column: str,
    low_light_column: str,
    split_column: str | None,
) -> dict[str, bool]:
    low_light_map: dict[str, bool] = {}
    with metadata_csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if split_column and row.get(split_column) not in {None, "", split_name}:
                continue
            filename = row.get(filename_column)
            low_light = _parse_bool(row.get(low_light_column))
            if not filename or low_light is None:
                continue
            low_light_map[Path(filename).as_posix()] = low_light
            low_light_map[Path(filename).name] = low_light
    return low_light_map


def load_ocr_benchmark_records(
    *,
    repo_root: Path,
    dataset_manifest_path: Path,
    split_name: str,
    metadata_csv_path: Path | None = None,
    metadata_filename_column: str = "filename",
    metadata_low_light_column: str = "fx_low_light",
    metadata_split_column: str | None = "split",
) -> tuple[object, list[OcrBenchmarkInputRecord]]:
    manifest = load_training_dataset_manifest(dataset_manifest_path)
    if manifest.format != DatasetFormat.ocr_manifest:
        raise ValueError("OCR preprocessing benchmark requires a dataset manifest with format=ocr_manifest")

    split_source = next((item for item in manifest.splits if item.split.value == split_name), None)
    if split_source is None:
        raise ValueError(f"dataset manifest '{manifest.dataset_name}' does not define split '{split_name}'")

    storage_root = _resolve_storage_root(repo_root, manifest.storage_root)
    labels_path = storage_root / split_source.label_path
    if not labels_path.exists():
        raise ValueError(f"missing OCR label file for split '{split_name}': {labels_path}")

    low_light_map: dict[str, bool] = {}
    if metadata_csv_path is not None:
        low_light_map = load_low_light_metadata(
            metadata_csv_path,
            split_name=split_name,
            filename_column=metadata_filename_column,
            low_light_column=metadata_low_light_column,
            split_column=metadata_split_column,
        )

    records: list[OcrBenchmarkInputRecord] = []
    with labels_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            image_key = str(row.get("image_file") or "").strip().replace("\\", "/")
            expected_text = str(row.get("plate_text") or row.get("text") or "").strip()
            if not image_key or not expected_text:
                continue
            image_path = _resolve_image_path(storage_root, split_source.relative_path, image_key)
            if not image_path.exists():
                raise ValueError(f"missing OCR image for split '{split_name}': {image_path}")
            low_light = low_light_map.get(image_key)
            if low_light is None:
                low_light = low_light_map.get(Path(image_key).name)
            records.append(
                OcrBenchmarkInputRecord(
                    image_key=image_key,
                    image_path=image_path,
                    expected_text=expected_text,
                    low_light=low_light,
                )
            )

    if not records:
        raise ValueError(f"no OCR benchmark rows were found for split '{split_name}' in {labels_path}")
    return manifest, records


def stage_ocr_benchmark_records(
    records: list[OcrBenchmarkInputRecord],
    *,
    preprocessing_service: PreprocessingService,
    raw_dir: Path,
    preprocessed_dir: Path,
    brightness_threshold: float,
) -> list[StagedOcrBenchmarkRecord]:
    staged: list[StagedOcrBenchmarkRecord] = []
    for record in records:
        raw_output = raw_dir / Path(record.image_key)
        raw_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.image_path, raw_output)

        preprocessed_output = preprocessed_dir / Path(record.image_key)
        preprocessed_output.parent.mkdir(parents=True, exist_ok=True)
        image, metadata = preprocessing_service.prepare_plate_crop_with_metadata(record.image_path)
        image.save(preprocessed_output)

        low_light = record.low_light
        low_light_source = "metadata_csv"
        if low_light is None:
            brightness_before = metadata.mean_brightness_before or 0.0
            low_light = brightness_before < brightness_threshold
            low_light_source = f"brightness_proxy<{brightness_threshold:.1f}"

        staged.append(
            StagedOcrBenchmarkRecord(
                image_key=record.image_key,
                expected_text=record.expected_text,
                raw_image_path=raw_output,
                preprocessed_image_path=preprocessed_output,
                low_light=bool(low_light),
                low_light_source=low_light_source,
                preprocessing=metadata.model_dump(mode="json"),
            )
        )
    return staged


def parse_paddleocr_results(results_path: Path, *, image_dir: Path) -> dict[str, dict[str, object]]:
    predictions: dict[str, dict[str, object]] = {}
    if not results_path.exists():
        raise ValueError(f"expected PaddleOCR results file was not created: {results_path}")

    resolved_image_dir = image_dir.resolve()
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            source_path = Path(parts[0]).resolve()
            try:
                image_key = source_path.relative_to(resolved_image_dir).as_posix()
            except ValueError:
                image_key = source_path.name
            confidence = None
            if len(parts) >= 3:
                try:
                    confidence = float(parts[2])
                except ValueError:
                    confidence = None
            predictions[image_key] = {
                "text": parts[1],
                "confidence": confidence,
            }
    return predictions


def run_paddleocr_inference(
    *,
    repo_root: Path,
    paddleocr_root: Path,
    paddle_config_path: Path,
    checkpoint_path: Path,
    character_dict_path: Path,
    image_dir: Path,
    results_path: Path,
) -> dict[str, dict[str, object]]:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    paddle_pythonpath = str(paddleocr_root.resolve())
    env["PYTHONPATH"] = paddle_pythonpath if not existing_pythonpath else os.pathsep.join([paddle_pythonpath, existing_pythonpath])

    command = [
        str(Path(sys.executable).resolve()),
        str((paddleocr_root / "tools" / "infer_rec.py").resolve()),
        "-c",
        str(paddle_config_path.resolve()),
        "-o",
        f"Global.pretrained_model={checkpoint_path.resolve().as_posix()}",
        f"Global.infer_img={image_dir.resolve().as_posix()}",
        f"Global.character_dict_path={character_dict_path.resolve().as_posix()}",
        f"Global.save_res_path={results_path.resolve().as_posix()}",
        "Global.use_gpu=False",
        "Global.distributed=False",
    ]
    result = subprocess.run(command, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "PaddleOCR inference failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return parse_paddleocr_results(results_path, image_dir=image_dir)


def _subset_metrics(results: list[dict]) -> dict[str, float | int | None]:
    if not results:
        return {
            "records": 0,
            "raw_exact_match": None,
            "preprocessed_exact_match": None,
            "exact_match_delta": None,
            "raw_character_accuracy": None,
            "preprocessed_character_accuracy": None,
            "character_accuracy_delta": None,
        }

    raw_exact = mean(1.0 if item["raw_exact_match"] else 0.0 for item in results)
    preprocessed_exact = mean(1.0 if item["preprocessed_exact_match"] else 0.0 for item in results)
    raw_char = mean(item["raw_character_accuracy"] for item in results)
    preprocessed_char = mean(item["preprocessed_character_accuracy"] for item in results)
    return {
        "records": len(results),
        "raw_exact_match": raw_exact,
        "preprocessed_exact_match": preprocessed_exact,
        "exact_match_delta": preprocessed_exact - raw_exact,
        "raw_character_accuracy": raw_char,
        "preprocessed_character_accuracy": preprocessed_char,
        "character_accuracy_delta": preprocessed_char - raw_char,
    }


def build_ocr_preprocessing_report(
    *,
    benchmark_name: str,
    dataset_manifest_path: Path,
    split_name: str,
    pipeline_config_path: Path,
    paddle_config_path: Path,
    checkpoint_path: Path,
    character_dict_path: Path,
    brightness_threshold: float,
    manifest,
    staged_records: list[StagedOcrBenchmarkRecord],
    raw_predictions: dict[str, dict[str, object]],
    preprocessed_predictions: dict[str, dict[str, object]],
) -> dict:
    results: list[dict] = []
    for record in staged_records:
        raw_prediction = raw_predictions.get(record.image_key, {})
        preprocessed_prediction = preprocessed_predictions.get(record.image_key, {})
        raw_text = str(raw_prediction.get("text") or "")
        preprocessed_text = str(preprocessed_prediction.get("text") or "")
        normalized_expected = normalize_ocr_text(record.expected_text)
        normalized_raw = normalize_ocr_text(raw_text)
        normalized_preprocessed = normalize_ocr_text(preprocessed_text)

        results.append(
            {
                "image_key": record.image_key,
                "expected_text": record.expected_text,
                "normalized_expected_text": normalized_expected,
                "raw_prediction": raw_text,
                "normalized_raw_prediction": normalized_raw,
                "raw_confidence": raw_prediction.get("confidence"),
                "preprocessed_prediction": preprocessed_text,
                "normalized_preprocessed_prediction": normalized_preprocessed,
                "preprocessed_confidence": preprocessed_prediction.get("confidence"),
                "raw_exact_match": normalized_expected == normalized_raw,
                "preprocessed_exact_match": normalized_expected == normalized_preprocessed,
                "raw_character_accuracy": character_accuracy(record.expected_text, raw_text),
                "preprocessed_character_accuracy": character_accuracy(record.expected_text, preprocessed_text),
                "low_light": record.low_light,
                "low_light_source": record.low_light_source,
                "preprocessing": record.preprocessing,
            }
        )

    low_light_results = [item for item in results if item["low_light"]]
    non_low_light_results = [item for item in results if not item["low_light"]]
    metadata_sourced = sum(1 for record in staged_records if record.low_light_source == "metadata_csv")
    preprocessing_metadata = [record.preprocessing for record in staged_records]

    return {
        "benchmark_name": benchmark_name,
        "generated_at_utc": _utcnow(),
        "dataset_name": manifest.dataset_name,
        "dataset_version": manifest.dataset_version,
        "dataset_manifest_path": str(dataset_manifest_path.resolve()),
        "dataset_review_status": manifest.review_status.value,
        "split": split_name,
        "pipeline_config_path": str(pipeline_config_path.resolve()),
        "paddle_config_path": str(paddle_config_path.resolve()),
        "checkpoint_path": str(checkpoint_path.resolve()),
        "character_dict_path": str(character_dict_path.resolve()),
        "brightness_threshold": brightness_threshold,
        "low_light_strategy": (
            "metadata_csv"
            if metadata_sourced == len(staged_records)
            else ("mixed" if metadata_sourced else f"brightness_proxy<{brightness_threshold:.1f}")
        ),
        "overall": _subset_metrics(results),
        "subsets": {
            "low_light": _subset_metrics(low_light_results),
            "non_low_light": _subset_metrics(non_low_light_results),
        },
        "preprocessing_summary": {
            "records": len(preprocessing_metadata),
            "mean_brightness_before": mean(
                item["mean_brightness_before"] for item in preprocessing_metadata if item["mean_brightness_before"] is not None
            ),
            "mean_brightness_after": mean(
                item["mean_brightness_after"] for item in preprocessing_metadata if item["mean_brightness_after"] is not None
            ),
            "night_mode_trigger_rate": mean(1.0 if item["night_mode_triggered"] else 0.0 for item in preprocessing_metadata),
            "exposure_adjusted_rate": mean(1.0 if item["exposure_adjusted"] else 0.0 for item in preprocessing_metadata),
            "denoise_applied_rate": mean(1.0 if item["denoise_applied"] else 0.0 for item in preprocessing_metadata),
            "contrast_enhanced_rate": mean(1.0 if item["contrast_enhanced"] else 0.0 for item in preprocessing_metadata),
            "clahe_applied_rate": mean(1.0 if item["clahe_applied"] else 0.0 for item in preprocessing_metadata),
        },
        "records": results,
    }
