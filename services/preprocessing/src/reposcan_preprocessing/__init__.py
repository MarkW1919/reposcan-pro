"""RepoScan Pro preprocessing service primitives."""

from .service import PreprocessingService
from .ocr_benchmark import (
    build_ocr_preprocessing_report,
    character_accuracy,
    load_ocr_benchmark_records,
    run_paddleocr_inference,
    stage_ocr_benchmark_records,
)

__all__ = [
    "PreprocessingService",
    "build_ocr_preprocessing_report",
    "character_accuracy",
    "load_ocr_benchmark_records",
    "run_paddleocr_inference",
    "stage_ocr_benchmark_records",
]
