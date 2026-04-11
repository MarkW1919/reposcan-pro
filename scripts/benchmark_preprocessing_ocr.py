from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "preprocessing" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def _find_paddle_config(root: Path) -> Path:
    candidates = [
        root / "configs" / "rec" / "PP-OCRv5" / "en_PP-OCRv5_rec.yml",
        root / "configs" / "rec" / "PP-OCRv5" / "en_PP-OCRv5_mobile_rec.yml",
        root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_rec.yml",
        root / "configs" / "rec" / "PP-OCRv4" / "en_PP-OCRv4_mobile_rec.yml",
        root / "configs" / "rec" / "PP-OCRv3" / "en_PP-OCRv3_rec.yml",
        root / "configs" / "rec" / "PP-OCRv3" / "en_PP-OCRv3_mobile_rec.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"could not find a PaddleOCR English recognition config under {root}")


def _resolve_path(repo_root: Path, raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark OCR exact match and character accuracy before and after RepoScan preprocessing."
    )
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--split", default="holdout")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--paddleocr-root", default="tmp/PaddleOCR")
    parser.add_argument("--paddle-config")
    parser.add_argument("--checkpoint-dir", default="tmp/PaddleOCR/en_PP-OCRv4_rec_train/best_accuracy")
    parser.add_argument("--character-dict-path", default="tmp/PaddleOCR/ppocr/utils/en_dict.txt")
    parser.add_argument("--metadata-csv")
    parser.add_argument("--metadata-filename-column", default="filename")
    parser.add_argument("--metadata-low-light-column", default="fx_low_light")
    parser.add_argument("--metadata-split-column", default="split")
    parser.add_argument("--brightness-threshold", type=float)
    parser.add_argument("--benchmark-name")
    parser.add_argument("--report-output")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import load_pipeline_config
    from reposcan_preprocessing import PreprocessingService
    from reposcan_preprocessing.ocr_benchmark import (
        build_ocr_preprocessing_report,
        load_ocr_benchmark_records,
        run_paddleocr_inference,
        stage_ocr_benchmark_records,
    )

    args = parse_args()
    dataset_manifest_path = _resolve_path(repo_root, args.dataset_manifest)
    pipeline_config_path = _resolve_path(repo_root, args.pipeline_config)
    paddleocr_root = _resolve_path(repo_root, args.paddleocr_root)
    paddle_config_path = _resolve_path(repo_root, args.paddle_config) if args.paddle_config else _find_paddle_config(paddleocr_root)
    checkpoint_path = _resolve_path(repo_root, args.checkpoint_dir)
    character_dict_path = _resolve_path(repo_root, args.character_dict_path)
    metadata_csv_path = _resolve_path(repo_root, args.metadata_csv)
    report_output = _resolve_path(repo_root, args.report_output)

    pipeline_config = load_pipeline_config(pipeline_config_path)
    brightness_threshold = (
        args.brightness_threshold
        if args.brightness_threshold is not None
        else float(pipeline_config.preprocessing.target_mean_brightness)
    )

    manifest, records = load_ocr_benchmark_records(
        repo_root=repo_root,
        dataset_manifest_path=dataset_manifest_path,
        split_name=args.split,
        metadata_csv_path=metadata_csv_path,
        metadata_filename_column=args.metadata_filename_column,
        metadata_low_light_column=args.metadata_low_light_column,
        metadata_split_column=args.metadata_split_column,
    )

    benchmark_name = args.benchmark_name or f"{manifest.dataset_name}-{args.split}-preprocessing-ocr"
    preprocessing_service = PreprocessingService(pipeline_config)

    with tempfile.TemporaryDirectory(prefix="reposcan_preprocessing_ocr_") as temp_dir:
        temp_root = Path(temp_dir)
        raw_dir = temp_root / "raw"
        preprocessed_dir = temp_root / "preprocessed"
        raw_results_path = temp_root / "raw_predictions.txt"
        preprocessed_results_path = temp_root / "preprocessed_predictions.txt"

        staged_records = stage_ocr_benchmark_records(
            records,
            preprocessing_service=preprocessing_service,
            raw_dir=raw_dir,
            preprocessed_dir=preprocessed_dir,
            brightness_threshold=brightness_threshold,
        )
        raw_predictions = run_paddleocr_inference(
            repo_root=repo_root,
            paddleocr_root=paddleocr_root,
            paddle_config_path=paddle_config_path,
            checkpoint_path=checkpoint_path,
            character_dict_path=character_dict_path,
            image_dir=raw_dir,
            results_path=raw_results_path,
        )
        preprocessed_predictions = run_paddleocr_inference(
            repo_root=repo_root,
            paddleocr_root=paddleocr_root,
            paddle_config_path=paddle_config_path,
            checkpoint_path=checkpoint_path,
            character_dict_path=character_dict_path,
            image_dir=preprocessed_dir,
            results_path=preprocessed_results_path,
        )

    report = build_ocr_preprocessing_report(
        benchmark_name=benchmark_name,
        dataset_manifest_path=dataset_manifest_path,
        split_name=args.split,
        pipeline_config_path=pipeline_config_path,
        paddle_config_path=paddle_config_path,
        checkpoint_path=checkpoint_path,
        character_dict_path=character_dict_path,
        brightness_threshold=brightness_threshold,
        manifest=manifest,
        staged_records=staged_records,
        raw_predictions=raw_predictions,
        preprocessed_predictions=preprocessed_predictions,
    )

    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Benchmark: {report['benchmark_name']}")
        print(f"Dataset: {report['dataset_name']} ({report['dataset_version']}) split={report['split']}")
        print(f"Review status: {report['dataset_review_status']}")
        print(f"Low-light strategy: {report['low_light_strategy']}")
        print(f"Overall raw exact match: {report['overall']['raw_exact_match']}")
        print(f"Overall preprocessed exact match: {report['overall']['preprocessed_exact_match']}")
        print(f"Overall raw character accuracy: {report['overall']['raw_character_accuracy']}")
        print(f"Overall preprocessed character accuracy: {report['overall']['preprocessed_character_accuracy']}")
        print(f"Low-light raw exact match: {report['subsets']['low_light']['raw_exact_match']}")
        print(f"Low-light preprocessed exact match: {report['subsets']['low_light']['preprocessed_exact_match']}")
        print(f"Low-light raw character accuracy: {report['subsets']['low_light']['raw_character_accuracy']}")
        print(f"Low-light preprocessed character accuracy: {report['subsets']['low_light']['preprocessed_character_accuracy']}")
        if report_output is not None:
            print(f"Report output: {report_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
