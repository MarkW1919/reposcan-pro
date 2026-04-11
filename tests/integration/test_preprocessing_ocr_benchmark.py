from __future__ import annotations

import csv
from pathlib import Path

import yaml
from PIL import Image

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_preprocessing import PreprocessingService
from reposcan_preprocessing.ocr_benchmark import (
    OcrBenchmarkInputRecord,
    StagedOcrBenchmarkRecord,
    build_ocr_preprocessing_report,
    load_ocr_benchmark_records,
    stage_ocr_benchmark_records,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_manifest(path: Path, *, storage_root: Path) -> None:
    payload = {
        "dataset_name": "ocr-benchmark-smoke",
        "dataset_version": "2026-04-11",
        "task": "plate_ocr",
        "format": "ocr_manifest",
        "storage_root": str(storage_root),
        "review_status": "approved",
        "provenance": {
            "source_name": "pytest",
            "source_kind": "internal_generated",
            "license_tier": "internal",
            "license_name": "internal",
            "license_reference": "internal://pytest",
            "region": "us-test",
        },
        "annotation_review": {
            "reviewer": "pytest",
            "reviewed_at_utc": "2026-04-11T00:00:00Z",
            "accepted_tasks": ["plate_ocr"],
        },
        "splits": [
            {
                "split": "holdout",
                "relative_path": "holdout/images",
                "label_path": "holdout/labels.csv",
                "sample_count": 2,
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_load_ocr_benchmark_records_uses_metadata_csv(tmp_path):
    dataset_root = tmp_path / "dataset"
    images_root = dataset_root / "holdout" / "images"
    images_root.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 24), color=(35, 35, 35)).save(images_root / "dark.png")
    Image.new("RGB", (80, 24), color=(220, 220, 220)).save(images_root / "bright.png")
    (dataset_root / "holdout" / "labels.csv").write_text(
        "image_file,plate_text\ndark.png,ABC123\nbright.png,XYZ987\n",
        encoding="utf-8",
    )
    metadata_csv = tmp_path / "metadata.csv"
    with metadata_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "filename", "fx_low_light"])
        writer.writeheader()
        writer.writerow({"split": "holdout", "filename": "holdout/images/dark.png", "fx_low_light": "True"})
        writer.writerow({"split": "holdout", "filename": "holdout/images/bright.png", "fx_low_light": "False"})

    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(manifest_path, storage_root=dataset_root)

    manifest, records = load_ocr_benchmark_records(
        repo_root=REPO_ROOT,
        dataset_manifest_path=manifest_path,
        split_name="holdout",
        metadata_csv_path=metadata_csv,
    )

    assert manifest.dataset_name == "ocr-benchmark-smoke"
    assert [record.image_key for record in records] == ["dark.png", "bright.png"]
    assert [record.low_light for record in records] == [True, False]


def test_stage_ocr_benchmark_records_derives_brightness_proxy_and_metadata(tmp_path):
    dark = tmp_path / "dark.png"
    bright = tmp_path / "bright.png"
    Image.new("RGB", (96, 32), color=(40, 40, 40)).save(dark)
    Image.new("RGB", (96, 32), color=(220, 220, 220)).save(bright)

    records = [
        OcrBenchmarkInputRecord(image_key="dark.png", image_path=dark, expected_text="ABC123"),
        OcrBenchmarkInputRecord(image_key="bright.png", image_path=bright, expected_text="XYZ987"),
    ]
    service = PreprocessingService(load_pipeline_config(str(REPO_ROOT / "configs/pipelines/default-edge.yaml")))
    staged = stage_ocr_benchmark_records(
        records,
        preprocessing_service=service,
        raw_dir=tmp_path / "raw",
        preprocessed_dir=tmp_path / "preprocessed",
        brightness_threshold=100.0,
    )

    assert len(staged) == 2
    assert staged[0].low_light is True
    assert staged[0].low_light_source == "brightness_proxy<100.0"
    assert staged[1].low_light is False
    assert staged[0].raw_image_path.exists()
    assert staged[0].preprocessed_image_path.exists()
    assert staged[0].preprocessing["mean_brightness_after"] is not None
    assert staged[0].preprocessing["enhancement_backend"] in {"opencv", "pillow"}


def test_build_ocr_preprocessing_report_computes_subset_metrics():
    staged_records = [
        StagedOcrBenchmarkRecord(
            image_key="dark.png",
            expected_text="ABC123",
            raw_image_path=Path("raw/dark.png"),
            preprocessed_image_path=Path("pre/dark.png"),
            low_light=True,
            low_light_source="metadata_csv",
            preprocessing={
                "artifact_generated": False,
                "enhancement_backend": "opencv",
                "denoise_applied": True,
                "exposure_adjusted": True,
                "contrast_enhanced": True,
                "clahe_applied": True,
                "night_mode_triggered": True,
                "mean_brightness_before": 72.0,
                "mean_brightness_after": 118.0,
            },
        ),
        StagedOcrBenchmarkRecord(
            image_key="bright.png",
            expected_text="XYZ987",
            raw_image_path=Path("raw/bright.png"),
            preprocessed_image_path=Path("pre/bright.png"),
            low_light=False,
            low_light_source="metadata_csv",
            preprocessing={
                "artifact_generated": False,
                "enhancement_backend": "opencv",
                "denoise_applied": True,
                "exposure_adjusted": False,
                "contrast_enhanced": True,
                "clahe_applied": True,
                "night_mode_triggered": False,
                "mean_brightness_before": 168.0,
                "mean_brightness_after": 175.0,
            },
        ),
    ]

    class _Manifest:
        dataset_name = "ocr-benchmark-smoke"
        dataset_version = "2026-04-11"

        class review_status:
            value = "approved"

    report = build_ocr_preprocessing_report(
        benchmark_name="ocr-benchmark-smoke",
        dataset_manifest_path=Path("manifest.yaml"),
        split_name="holdout",
        pipeline_config_path=REPO_ROOT / "configs/pipelines/default-edge.yaml",
        paddle_config_path=Path("tmp/PaddleOCR/config.yml"),
        checkpoint_path=Path("tmp/PaddleOCR/checkpoint"),
        character_dict_path=Path("tmp/PaddleOCR/ppocr/utils/en_dict.txt"),
        brightness_threshold=90.0,
        manifest=_Manifest(),
        staged_records=staged_records,
        raw_predictions={
            "dark.png": {"text": "ABC128", "confidence": 0.7},
            "bright.png": {"text": "XYZ987", "confidence": 0.9},
        },
        preprocessed_predictions={
            "dark.png": {"text": "ABC123", "confidence": 0.8},
            "bright.png": {"text": "XYZ987", "confidence": 0.92},
        },
    )

    assert report["overall"]["records"] == 2
    assert report["overall"]["raw_exact_match"] == 0.5
    assert report["overall"]["preprocessed_exact_match"] == 1.0
    assert report["overall"]["exact_match_delta"] == 0.5
    assert report["subsets"]["low_light"]["preprocessed_exact_match"] == 1.0
    assert report["subsets"]["non_low_light"]["raw_exact_match"] == 1.0
    assert report["preprocessing_summary"]["night_mode_trigger_rate"] == 0.5
