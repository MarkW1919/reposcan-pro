from __future__ import annotations

import csv
import importlib.util
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


def _load_module():
    module_path = REPO_ROOT / "scripts" / "suggest_capture_detections.py"
    spec = importlib.util.spec_from_file_location("suggest_capture_detections", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_predict_ultralytics_vehicle_detections_filters_to_vehicle_labels(monkeypatch, tmp_path):
    module = _load_module()

    class _FakeTensor:
        def __init__(self, values):
            self._values = values

        def cpu(self):
            return self

        def tolist(self):
            return self._values

    class _FakeBoxes:
        xyxy = _FakeTensor([[10, 20, 110, 120], [5, 6, 15, 16]])
        conf = _FakeTensor([0.91, 0.88])
        cls = _FakeTensor([2, 0])

    class _FakeResult:
        boxes = _FakeBoxes()
        names = {0: "person", 2: "car"}

    class _FakeModel:
        def predict(self, **kwargs):
            return [_FakeResult()]

    monkeypatch.setattr(module, "_load_ultralytics_model", lambda model_name: _FakeModel())
    image_path = tmp_path / "frame.jpg"
    _write_image(image_path, color=(10, 10, 10))

    detections = module._predict_ultralytics_vehicle_detections(
        image_path,
        model_name="fake.pt",
        device="cpu",
        min_confidence=0.1,
        accepted_labels={"car", "truck"},
    )

    assert len(detections) == 1
    assert detections[0].class_label == "car"
    assert detections[0].bbox.w == 100
