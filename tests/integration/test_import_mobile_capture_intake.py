from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import yaml


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "import_mobile_capture_intake.py"
    spec = importlib.util.spec_from_file_location("import_mobile_capture_intake", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_capture(root: Path, *, day: str, session: str, capture_id: str, capture_type: str = "vehicle") -> None:
    session_root = root / day / session
    session_root.mkdir(parents=True, exist_ok=True)
    image_path = session_root / f"{capture_id}.jpg"
    metadata_path = session_root / f"{capture_id}.json"
    image_path.write_bytes(b"fake-jpeg-bytes")
    payload = {
        "captureId": capture_id,
        "timestampUtc": f"{day}T18:00:00Z",
        "sessionId": session,
        "deviceLabel": "galaxy_s23_dash",
        "captureType": capture_type,
        "gps": {"latitude": 35.5, "longitude": -97.5, "accuracyMeters": 4.0},
        "headingDegrees": 90.0,
        "speedMps": 0.0,
        "imageFilename": image_path.name,
        "remoteAddress": "203.0.113.10",
    }
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_import_mobile_capture_intake_writes_manifest_and_review_index(tmp_path, monkeypatch):
    module = _load_module()
    capture_root = tmp_path / "incoming"
    output_root = tmp_path / "staged_mobile_capture"
    manifest_path = tmp_path / "mobile_capture.yaml"
    review_csv = tmp_path / "review_index.csv"
    state_path = tmp_path / "state.json"
    _write_capture(capture_root, day="2026-04-18", session="ok_test_20260418", capture_id="capture_001")
    _write_capture(capture_root, day="2026-04-18", session="ok_test_20260418", capture_id="capture_002")

    monkeypatch.setattr(
        "sys.argv",
        [
            "import_mobile_capture_intake.py",
            "--capture-root",
            str(capture_root),
            "--output-root",
            str(output_root),
            "--manifest-path",
            str(manifest_path),
            "--review-csv",
            str(review_csv),
            "--dataset-name",
            "mobile-capture-intake-test",
            "--state-path",
            str(state_path),
            "--copy-mode",
            "copy",
            "--overwrite-manifest",
        ],
    )

    result = module.main()

    assert result == 0
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["dataset_name"] == "mobile-capture-intake-test"
    assert manifest["format"] == "generic_capture"
    assert manifest["review_status"] == "pending"
    assert len(manifest["assets"]) == 2

    rows = list(csv.DictReader(review_csv.open("r", encoding="utf-8", newline="")))
    assert len(rows) == 2
    assert rows[0]["reposcan_reviewed"] == "false"
    assert rows[0]["reposcan_accepted"] == "false"
    assert rows[0]["capture_session_id"] == "ok_test_20260418"

    imported_image = output_root / rows[0]["image_relative_path"]
    imported_metadata = output_root / rows[0]["metadata_relative_path"]
    assert imported_image.exists()
    assert imported_metadata.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state["imported_metadata_paths"]) == 2


def test_import_mobile_capture_intake_is_incremental(tmp_path, monkeypatch):
    module = _load_module()
    capture_root = tmp_path / "incoming"
    output_root = tmp_path / "staged_mobile_capture"
    manifest_path = tmp_path / "mobile_capture.yaml"
    review_csv = tmp_path / "review_index.csv"
    state_path = tmp_path / "state.json"
    _write_capture(capture_root, day="2026-04-18", session="route_a", capture_id="capture_001")

    first_argv = [
        "import_mobile_capture_intake.py",
        "--capture-root",
        str(capture_root),
        "--output-root",
        str(output_root),
        "--manifest-path",
        str(manifest_path),
        "--review-csv",
        str(review_csv),
        "--dataset-name",
        "mobile-capture-intake-test",
        "--state-path",
        str(state_path),
        "--copy-mode",
        "copy",
        "--overwrite-manifest",
    ]
    monkeypatch.setattr("sys.argv", first_argv)
    assert module.main() == 0

    _write_capture(capture_root, day="2026-04-18", session="route_b", capture_id="capture_002")
    monkeypatch.setattr("sys.argv", first_argv)
    assert module.main() == 0

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["assets"]) == 2
    rows = list(csv.DictReader(review_csv.open("r", encoding="utf-8", newline="")))
    assert len(rows) == 2
    sessions = {row["capture_session_id"] for row in rows}
    assert sessions == {"route_a", "route_b"}

