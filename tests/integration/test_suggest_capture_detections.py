from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_image(path: Path, *, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=color).save(path)


def _write_metadata(path: Path, *, session: str, capture_id: str) -> None:
    payload = {
        "captureId": capture_id,
        "timestampUtc": "2026-04-18T18:50:13.360Z",
        "sessionId": session,
        "deviceLabel": "android_dash_mount",
        "captureType": "vehicle",
        "gps": {"latitude": 33.8574395, "longitude": -96.5149339, "accuracyMeters": 3.79},
        "headingDegrees": 37.0,
        "speedMps": 0.34,
        "imageFilename": f"{capture_id}.jpg",
        "remoteAddress": "203.0.113.25",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_manifest(path: Path, storage_root: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "dataset_name: mobile-capture-intake-test",
                "dataset_version: 2026-04-18",
                "task: vehicle_detection",
                "format: generic_capture",
                f"storage_root: {storage_root.as_posix()}",
                "review_status: pending",
                "provenance:",
                "  source_name: RepoScan mobile capture intake",
                "  source_kind: field_capture",
                "  license_tier: internal",
                "  license_name: internal field capture",
                "  license_reference: internal://reposcan/mobile-capture",
                "assets:",
                "  - asset_id: asset_001",
                "    relative_path: raw/2026-04-18/ok_test_20260418/capture_001.jpg",
                "    capture_session_id: ok_test_20260418",
                "    timestamp_utc: 2026-04-18T18:50:13.360Z",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_suggest_capture_detections_writes_review_csv_and_crops(tmp_path):
    storage_root = tmp_path / "staged"
    image_path = storage_root / "raw" / "2026-04-18" / "ok_test_20260418" / "capture_001.jpg"
    metadata_path = image_path.with_suffix(".json")
    _write_image(image_path, color=(60, 80, 160))
    _write_metadata(metadata_path, session="ok_test_20260418", capture_id="capture_001")

    manifest_path = tmp_path / "mobile_capture.yaml"
    _write_manifest(manifest_path, storage_root)

    output_root = tmp_path / "review_output"
    result = _run_script(
        "scripts/suggest_capture_detections.py",
        "--dataset-manifest",
        str(manifest_path),
        "--output-root",
        str(output_root),
        "--model-config",
        str(REPO_ROOT / "configs" / "models" / "local-demo-runtime.yaml"),
        "--overwrite",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    review_csv = output_root / "metadata" / "detection_review.csv"
    frame_summary = output_root / "metadata" / "frame_summary.csv"
    candidates_jsonl = output_root / "metadata" / "inference_candidates.jsonl"
    assert review_csv.exists()
    assert frame_summary.exists()
    assert candidates_jsonl.exists()

    review_rows = list(csv.DictReader(review_csv.open("r", encoding="utf-8", newline="")))
    assert len(review_rows) == 2
    assert {row["detection_kind"] for row in review_rows} == {"vehicle", "plate"}
    assert any((output_root / row["crop_relative_path"]).exists() for row in review_rows)

    summary_rows = list(csv.DictReader(frame_summary.open("r", encoding="utf-8", newline="")))
    assert len(summary_rows) == 1
    assert summary_rows[0]["vehicle_detection_count"] == "1"
    assert summary_rows[0]["plate_detection_count"] == "1"

    candidate_lines = candidates_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(candidate_lines) == 1


def test_suggest_capture_detections_respects_detection_kind_filter(tmp_path):
    storage_root = tmp_path / "staged"
    image_path = storage_root / "raw" / "2026-04-18" / "ok_test_20260418" / "capture_001.jpg"
    metadata_path = image_path.with_suffix(".json")
    _write_image(image_path, color=(140, 140, 140))
    _write_metadata(metadata_path, session="ok_test_20260418", capture_id="capture_001")

    manifest_path = tmp_path / "mobile_capture.yaml"
    _write_manifest(manifest_path, storage_root)

    output_root = tmp_path / "review_output"
    result = _run_script(
        "scripts/suggest_capture_detections.py",
        "--dataset-manifest",
        str(manifest_path),
        "--output-root",
        str(output_root),
        "--model-config",
        str(REPO_ROOT / "configs" / "models" / "local-demo-runtime.yaml"),
        "--detection-kind",
        "vehicle",
        "--overwrite",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    review_csv = output_root / "metadata" / "detection_review.csv"
    review_rows = list(csv.DictReader(review_csv.open("r", encoding="utf-8", newline="")))
    assert len(review_rows) == 1
    assert review_rows[0]["detection_kind"] == "vehicle"
    assert review_rows[0]["suggested_make"] != ""
