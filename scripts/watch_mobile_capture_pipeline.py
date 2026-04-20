from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CAPTURE_ROOT = Path(r"C:\ReposcanCaptureData\incoming")
DEFAULT_ULTRALYTICS_MODEL = Path("runtime/models/ultralytics/yolov8s.pt")
DEFAULT_STATE_PATH = Path("runtime/capture_import_state/mobile_capture_import_state_20260420.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today_slug() -> str:
    return datetime.now().strftime("%Y%m%d")


def parse_args() -> argparse.Namespace:
    today = _today_slug()
    parser = argparse.ArgumentParser(
        description=(
            "Watch mobile PWA uploads and keep a live auto-processing inbox refreshed without "
            "touching human-reviewed queues."
        )
    )
    parser.add_argument("--capture-root", default=str(DEFAULT_CAPTURE_ROOT))
    parser.add_argument("--dataset-name", default=f"mobile_capture_live_intake_{today}")
    parser.add_argument("--output-root", default=f"data/staged/mobile_capture_live_intake_{today}")
    parser.add_argument("--manifest-path", default=f"data/manifests/staged/mobile-capture-live-intake-{today}.yaml")
    parser.add_argument("--detection-output-root", default=f"data/staged/mobile_capture_live_detection_review_{today}")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--ultralytics-model", default=str(DEFAULT_ULTRALYTICS_MODEL))
    parser.add_argument("--ultralytics-imgsz", type=int, default=960)
    parser.add_argument("--min-vehicle-confidence", type=float, default=0.10)
    parser.add_argument("--interval-seconds", type=int, default=180)
    parser.add_argument("--settle-seconds", type=int, default=20)
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--force", action="store_true", help="Run import and downstream processing even when uploads have not changed.")
    parser.add_argument(
        "--no-retry-failed",
        action="store_false",
        dest="retry_failed",
        help="Disable automatic retry of incomplete or failed downstream processing after import.",
    )
    parser.add_argument("--skip-detection", action="store_true", help="Only run import; useful for quick smoke tests.")
    parser.add_argument("--log-dir", default="runtime/mobile_capture_pipeline_watcher")
    return parser.parse_args()


def _resolve(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _capture_fingerprint(capture_root: Path) -> dict[str, int]:
    if not capture_root.exists():
        return {"count": 0, "latest_mtime_ns": 0}

    count = 0
    latest_mtime_ns = 0
    for path in capture_root.rglob("*.json"):
        if not path.is_file() or path.name.lower() == "captures.jsonl":
            continue
        count += 1
        try:
            latest_mtime_ns = max(latest_mtime_ns, path.stat().st_mtime_ns)
        except OSError:
            continue
    return {"count": count, "latest_mtime_ns": latest_mtime_ns}


def _count_metadata_files(capture_root: Path) -> int:
    return _capture_fingerprint(capture_root)["count"]


def _run_command(
    command: list[str],
    *,
    repo_root: Path,
    log_path: Path,
) -> tuple[int, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = _utc_now()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"\n=== {started} :: {' '.join(command)} ===\n")
        handle.write(output)
        if output and not output.endswith("\n"):
            handle.write("\n")
        handle.write(f"=== exit_code={completed.returncode} ===\n")
    return completed.returncode, output


def _parse_imported_now(output: str) -> int:
    start = output.find("{")
    end = output.rfind("}")
    if start < 0 or end < start:
        return 0
    try:
        payload = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return 0
    try:
        return int(payload.get("imported_now") or 0)
    except (TypeError, ValueError):
        return 0


def _write_status(status_path: Path, payload: dict[str, Any]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_status(status_path: Path) -> dict[str, Any]:
    if not status_path.exists():
        return {}
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _processing_outputs_missing(args: argparse.Namespace, repo_root: Path) -> bool:
    manifest_path = _resolve(repo_root, args.manifest_path)
    detection_output_root = _resolve(repo_root, args.detection_output_root)
    detection_csv = detection_output_root / "metadata" / "detection_review.csv"
    vehicle_priority_csv = detection_output_root / "metadata" / "vehicle_attribute_priority_review_no_runtime_attrs.csv"
    plate_priority_csv = detection_output_root / "metadata" / "plate_ocr_priority_review.csv"
    return manifest_path.exists() and not (
        detection_csv.exists() and vehicle_priority_csv.exists() and plate_priority_csv.exists()
    )


def _should_process_existing(args: argparse.Namespace, repo_root: Path, status_path: Path) -> bool:
    if args.force:
        return True
    if _processing_outputs_missing(args, repo_root):
        return True
    if not args.retry_failed:
        return False
    previous_status = _read_status(status_path)
    if previous_status.get("status") in {"failed", "running"}:
        return previous_status.get("failed_stage") != "import"
    return False


def _pipeline_commands(args: argparse.Namespace, repo_root: Path) -> dict[str, list[str]]:
    python = sys.executable
    output_root = _resolve(repo_root, args.output_root)
    manifest_path = _resolve(repo_root, args.manifest_path)
    detection_output_root = _resolve(repo_root, args.detection_output_root)
    state_path = _resolve(repo_root, args.state_path)
    ultralytics_model = _resolve(repo_root, args.ultralytics_model)
    detection_csv = detection_output_root / "metadata" / "detection_review.csv"
    vehicle_review_csv = detection_output_root / "metadata" / "vehicle_attribute_review_no_runtime_attrs.csv"

    return {
        "import": [
            python,
            "scripts/import_mobile_capture_intake.py",
            "--capture-root",
            str(Path(args.capture_root).resolve()),
            "--output-root",
            str(output_root),
            "--manifest-path",
            str(manifest_path),
            "--review-csv",
            str(output_root / "metadata" / "review_index.csv"),
            "--dataset-name",
            args.dataset_name,
            "--state-path",
            str(state_path),
            "--task",
            "vehicle_detection",
            "--copy-mode",
            "hardlink",
            "--overwrite-manifest",
        ],
        "detect": [
            python,
            "scripts/suggest_capture_detections.py",
            "--dataset-manifest",
            str(manifest_path),
            "--output-root",
            str(detection_output_root),
            "--vehicle-detector-provider",
            "ultralytics-coco",
            "--ultralytics-model",
            str(ultralytics_model),
            "--ultralytics-imgsz",
            str(args.ultralytics_imgsz),
            "--detection-kind",
            "both",
            "--disable-preprocessing",
            "--min-vehicle-confidence",
            str(args.min_vehicle_confidence),
            "--overwrite",
        ],
        "vehicle_attributes": [
            python,
            "scripts/prepare_mobile_capture_attribute_review.py",
            "--detection-review-csv",
            str(detection_csv),
            "--output-csv",
            str(vehicle_review_csv),
            "--drop-runtime-attribute-suggestions",
            "--overwrite",
        ],
        "plate_priority": [
            python,
            "scripts/prepare_mobile_capture_priority_review.py",
            "plate-ocr",
            "--input-csv",
            str(detection_csv),
            "--output-csv",
            str(detection_output_root / "metadata" / "plate_ocr_priority_review.csv"),
            "--max-per-group",
            "5",
            "--overwrite",
        ],
        "vehicle_priority": [
            python,
            "scripts/prepare_mobile_capture_priority_review.py",
            "vehicle-attributes",
            "--input-csv",
            str(vehicle_review_csv),
            "--output-csv",
            str(detection_output_root / "metadata" / "vehicle_attribute_priority_review_no_runtime_attrs.csv"),
            "--max-per-group",
            "5",
            "--overwrite",
        ],
    }


def run_pipeline_once(
    args: argparse.Namespace,
    *,
    repo_root: Path,
    status_path: Path,
    log_path: Path,
    process_existing: bool = False,
) -> dict[str, Any]:
    commands = _pipeline_commands(args, repo_root)
    started = _utc_now()
    capture_fingerprint = _capture_fingerprint(Path(args.capture_root))
    status: dict[str, Any] = {
        "started_utc": started,
        "status": "running",
        "capture_metadata_count": capture_fingerprint["count"],
        "capture_latest_mtime_ns": capture_fingerprint["latest_mtime_ns"],
        "process_existing": process_existing,
        "commands": {},
    }
    _write_status(status_path, status)

    import_code, import_output = _run_command(commands["import"], repo_root=repo_root, log_path=log_path)
    imported_now = _parse_imported_now(import_output)
    status["commands"]["import"] = {"exit_code": import_code, "imported_now": imported_now}
    if import_code != 0:
        status.update({"status": "failed", "failed_stage": "import", "completed_utc": _utc_now()})
        _write_status(status_path, status)
        return status

    if args.skip_detection or (imported_now == 0 and not process_existing):
        status.update({"status": "idle" if imported_now == 0 else "imported", "completed_utc": _utc_now()})
        _write_status(status_path, status)
        return status

    for stage in ("detect", "vehicle_attributes", "plate_priority", "vehicle_priority"):
        exit_code, _ = _run_command(commands[stage], repo_root=repo_root, log_path=log_path)
        status["commands"][stage] = {"exit_code": exit_code}
        _write_status(status_path, status)
        if exit_code != 0:
            status.update({"status": "failed", "failed_stage": stage, "completed_utc": _utc_now()})
            _write_status(status_path, status)
            return status

    status.update(
        {
            "status": "processed",
            "completed_utc": _utc_now(),
            "detection_output_root": str(_resolve(repo_root, args.detection_output_root)),
        }
    )
    _write_status(status_path, status)
    return status


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    log_dir = _resolve(repo_root, args.log_dir)
    status_path = log_dir / "status.json"
    log_path = log_dir / "pipeline.log"
    capture_root = Path(args.capture_root)

    previous_fingerprint = _capture_fingerprint(capture_root)
    first_loop = True
    print(
        json.dumps(
            {
                "status": "watching",
                "capture_root": str(capture_root.resolve()),
                "initial_metadata_count": previous_fingerprint["count"],
                "initial_latest_mtime_ns": previous_fingerprint["latest_mtime_ns"],
                "interval_seconds": args.interval_seconds,
                "status_path": str(status_path),
                "log_path": str(log_path),
                "pid": os.getpid(),
            },
            indent=2,
        ),
        flush=True,
    )

    while True:
        current_fingerprint = _capture_fingerprint(capture_root)
        process_existing = _should_process_existing(args, repo_root, status_path) if first_loop or args.force else False
        should_run = first_loop or process_existing or current_fingerprint != previous_fingerprint or args.force
        if should_run:
            if args.settle_seconds > 0:
                time.sleep(args.settle_seconds)
            status = run_pipeline_once(
                args,
                repo_root=repo_root,
                status_path=status_path,
                log_path=log_path,
                process_existing=process_existing,
            )
            previous_fingerprint = _capture_fingerprint(capture_root)
            if status.get("status") == "failed" and args.retry_failed:
                previous_fingerprint = {"count": -1, "latest_mtime_ns": -1}
            print(json.dumps(status, indent=2), flush=True)

        if args.run_once:
            return 0
        first_loop = False
        time.sleep(max(args.interval_seconds, 1))


if __name__ == "__main__":
    raise SystemExit(main())
