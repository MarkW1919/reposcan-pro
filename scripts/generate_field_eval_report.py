"""generate_field_eval_report.py — Run a field-eval scenario against a holdout manifest.

Iterates over the assets in a FieldEvalHoldoutManifest, runs the full inference
pipeline on each frame, computes per-dimension metrics, compares against the
acceptance thresholds, and writes a FieldEvalReport YAML.

When the holdout has no assets yet (status=pending) the report is generated with
zero assets evaluated, all dimensions skipped, and overall_passed=None.  This
lets CI gate on the report file existing without blocking on real data.

Usage:
    python scripts/generate_field_eval_report.py \\
        --holdout-manifest data/datasets/field-eval-holdouts/night-v1.yaml \\
        --model-config configs/models/default-edge.yaml \\
        --report-output runtime/field-eval/night-v1-report.yaml

    python scripts/generate_field_eval_report.py \\
        --holdout-manifest data/datasets/field-eval-holdouts/long-range-v1.yaml \\
        --model-config configs/models/default-edge.yaml \\
        --model-stack-name reposcan-edge-v0.1.0 \\
        --hardware-description "Jetson AGX Orin 64 GB, JetPack 6.1, TensorRT 10.0.1" \\
        --report-output runtime/field-eval/long-range-v1-report.yaml \\
        --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "capture" / "src",
        repo_root / "services" / "preprocessing" / "src",
        repo_root / "services" / "inference" / "src",
        repo_root / "services" / "tracking" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a FieldEvalReport by running inference against a holdout manifest."
    )
    parser.add_argument("--holdout-manifest", required=True,
        help="Path to a FieldEvalHoldoutManifest YAML file.")
    parser.add_argument("--model-config", required=True,
        help="Path to a ModelStackConfig YAML file.")
    parser.add_argument("--pipeline-config", default="configs/pipelines/default-edge.yaml")
    parser.add_argument("--model-stack-name", default=None,
        help="Human-readable model stack identifier for the report. Defaults to model config name.")
    parser.add_argument("--hardware-description", default=None,
        help="Description of the hardware used, e.g. 'Jetson AGX Orin 64 GB'.")
    parser.add_argument("--report-output", required=True,
        help="Path to write the FieldEvalReport YAML.")
    parser.add_argument("--json", action="store_true", dest="as_json",
        help="Also print the report as JSON to stdout.")
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _cer(expected: str, actual: str) -> float:
    """Character error rate as 1 - (correct / len(expected)), clipped to [0, 1]."""
    if not expected:
        return 0.0 if not actual else 1.0
    matched = sum(a == b for a, b in zip(expected, actual))
    return max(0.0, 1.0 - matched / len(expected))


def _run_inference_on_asset(
    asset_path: Path,
    repo_root: Path,
    inference_service,
    preprocessing_service,
) -> dict:
    """Run preprocessing + inference on one frame file.

    Returns a dict with keys: plate_text, latency_ms, vehicle_detected, plate_detected.
    Returns None values if the file does not exist yet (pending holdout).
    """
    if not asset_path.exists():
        return {"plate_text": None, "latency_ms": None, "vehicle_detected": None, "plate_detected": None}

    import cv2
    frame_bgr = cv2.imread(str(asset_path))
    if frame_bgr is None:
        return {"plate_text": None, "latency_ms": None, "vehicle_detected": None, "plate_detected": None}

    t0 = time.perf_counter()
    prepared = preprocessing_service.prepare(frame_bgr)
    candidates = inference_service.run(prepared)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    best_plate = None
    vehicle_detected = False
    plate_detected = False

    for candidate in candidates:
        vehicle_detected = True
        if candidate.plate and candidate.plate.ocr_text:
            plate_detected = True
            if best_plate is None or (candidate.plate.ocr_confidence or 0) > (
                candidates[0].plate.ocr_confidence or 0
            ):
                best_plate = candidate.plate.ocr_text

    return {
        "plate_text": best_plate,
        "latency_ms": latency_ms,
        "vehicle_detected": vehicle_detected,
        "plate_detected": plate_detected,
    }


def _build_empty_report(holdout, model_stack_name: str, hardware_description: str | None) -> dict:
    """Return a report dict with no assets evaluated (pending holdout)."""
    return {
        "holdout_name": holdout.holdout_name,
        "scenario": holdout.scenario.value,
        "model_stack_name": model_stack_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "hardware_description": hardware_description,
        "total_assets_evaluated": 0,
        "dimensions": [],
        "overall_passed": None,
        "export_viable": None,
        "notes": (
            f"Holdout '{holdout.holdout_name}' has no assets yet (status={holdout.status}). "
            "Report generated as a placeholder. Re-run once field data is collected and reviewed."
        ),
    }


def _compute_dimension(
    name: str,
    value: float | None,
    threshold: float | None,
    sample_count: int,
    higher_is_better: bool = True,
    notes: str | None = None,
) -> dict:
    passed: bool | None = None
    if value is not None and threshold is not None:
        passed = (value >= threshold) if higher_is_better else (value <= threshold)
    return {
        "dimension": name,
        "value": value,
        "threshold": threshold,
        "passed": passed,
        "sample_count": sample_count,
        "notes": notes,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.config.loader import (
        load_field_eval_holdout_manifest,
        load_model_config,
        load_pipeline_config,
    )
    from reposcan_contracts.field_eval import FieldEvalReport

    args = parse_args()
    holdout_path = _resolve_path(repo_root, args.holdout_manifest)
    model_config_path = _resolve_path(repo_root, args.model_config)
    report_output_path = _resolve_path(repo_root, args.report_output)

    holdout = load_field_eval_holdout_manifest(holdout_path)
    model_config = load_model_config(model_config_path)

    model_stack_name = args.model_stack_name or model_config.stack_name
    hardware_description = args.hardware_description

    # ── Empty holdout — generate placeholder report ───────────────────────────
    if not holdout.assets:
        report_data = _build_empty_report(holdout, model_stack_name, hardware_description)
        _write_yaml(report_output_path, report_data)
        # Validate the report schema
        report = FieldEvalReport.model_validate(report_data)

        if args.as_json:
            print(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
        else:
            print(f"Holdout '{holdout.holdout_name}' has no assets — placeholder report written.")
            print(f"Report: {report_output_path}")
        return 0

    # ── Load inference pipeline ───────────────────────────────────────────────
    pipeline_config = load_pipeline_config(
        _resolve_path(repo_root, args.pipeline_config)
    )

    try:
        from reposcan_preprocessing.service import PreprocessingService  # type: ignore[import-not-found]
        from reposcan_inference.adapters import build_inference_adapter  # type: ignore[import-not-found]
        preprocessing = PreprocessingService()
        inference = build_inference_adapter(model_config, pipeline_config)
    except ImportError as exc:
        print(f"ERROR: Could not import inference services: {exc}", file=sys.stderr)
        print("Make sure the virtual environment is active and services are installed.", file=sys.stderr)
        return 1

    # ── Run inference on each asset ───────────────────────────────────────────
    holdout_root = _resolve_path(repo_root, holdout.holdout_root)
    exact_matches: list[bool] = []
    char_accuracies: list[float] = []
    latencies: list[float] = []
    vehicles_detected: list[bool] = []
    plates_detected: list[bool] = []

    missing = 0
    for asset in holdout.assets:
        asset_path = holdout_root / asset.relative_path
        result = _run_inference_on_asset(asset_path, repo_root, inference, preprocessing)

        if result["latency_ms"] is None:
            missing += 1
            continue

        latencies.append(result["latency_ms"])
        vehicles_detected.append(bool(result["vehicle_detected"]))
        plates_detected.append(bool(result["plate_detected"]))

        if asset.expected_plate_text and result["plate_text"] is not None:
            expected = "".join(c for c in asset.expected_plate_text.upper() if c.isalnum())
            actual = "".join(c for c in result["plate_text"].upper() if c.isalnum())
            exact_matches.append(expected == actual)
            char_accuracies.append(1.0 - _cer(expected, actual))

    n = len(latencies)
    a = holdout.acceptance

    def _safe_mean(lst: list) -> float | None:
        return sum(lst) / len(lst) if lst else None

    def _safe_p95(lst: list) -> float | None:
        if not lst:
            return None
        s = sorted(lst)
        idx = max(0, int(len(s) * 0.95) - 1)
        return s[idx]

    exact_match_rate = _safe_mean([float(v) for v in exact_matches]) if exact_matches else None
    char_accuracy = _safe_mean(char_accuracies) if char_accuracies else None
    avg_latency = _safe_mean(latencies)
    p95_latency = _safe_p95(latencies)
    detection_rate = _safe_mean([float(v) for v in vehicles_detected]) if vehicles_detected else None
    plate_detection_rate = _safe_mean([float(v) for v in plates_detected]) if plates_detected else None

    dimensions = [
        _compute_dimension("exact_match", exact_match_rate, a.min_exact_match_rate,
                           len(exact_matches), higher_is_better=True),
        _compute_dimension("character_accuracy", char_accuracy, a.min_character_accuracy,
                           len(char_accuracies), higher_is_better=True),
        _compute_dimension("average_latency_ms", avg_latency, a.max_average_latency_ms,
                           n, higher_is_better=False),
        _compute_dimension("p95_latency_ms", p95_latency, a.max_p95_latency_ms,
                           n, higher_is_better=False),
        _compute_dimension("detection_rate", detection_rate, a.min_detection_rate,
                           n, higher_is_better=True),
        _compute_dimension("plate_detection_rate", plate_detection_rate, a.min_plate_detection_rate,
                           n, higher_is_better=True),
    ]

    # Overall pass: all dimensions that have both value and threshold must pass
    enforced = [d for d in dimensions if d["passed"] is not None]
    overall_passed: bool | None = all(d["passed"] for d in enforced) if enforced else None
    export_viable = (exact_match_rate is not None and exact_match_rate >= 0.50)

    report_data = {
        "holdout_name": holdout.holdout_name,
        "scenario": holdout.scenario.value,
        "model_stack_name": model_stack_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "hardware_description": hardware_description,
        "total_assets_evaluated": n,
        "dimensions": dimensions,
        "overall_passed": overall_passed,
        "export_viable": export_viable,
        "notes": f"{missing} asset(s) skipped (files not found)." if missing else None,
    }

    _write_yaml(report_output_path, report_data)
    report = FieldEvalReport.model_validate(report_data)

    if args.as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
    else:
        status_str = "PASSED" if overall_passed else ("FAILED" if overall_passed is False else "INCOMPLETE")
        print(f"Field eval: {holdout.holdout_name} / {holdout.scenario.value}")
        print(f"  Assets evaluated : {n}")
        print(f"  Overall          : {status_str}")
        for d in dimensions:
            if d["value"] is not None:
                indicator = "✓" if d["passed"] else ("✗" if d["passed"] is False else "–")
                print(f"  {indicator} {d['dimension']:30s} {d['value']:.4f}  (threshold: {d['threshold']})")
        print(f"  Export viable    : {export_viable}")
        print(f"Report written to: {report_output_path}")

    return 0 if overall_passed is not False else 1


if __name__ == "__main__":
    sys.exit(main())
