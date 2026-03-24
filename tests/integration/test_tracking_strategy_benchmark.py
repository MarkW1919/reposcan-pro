from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.inference import AttributePredictions, InferenceCandidate, ModelVersions
from reposcan_tracking import TrackingService, benchmark_tracking_strategies


REPO_ROOT = Path(__file__).resolve().parents[2]


def _frame(frame_number: int, timestamp_utc: str) -> FrameEnvelope:
    return FrameEnvelope.model_validate(
        {
            "frame_id": f"trk_test_{frame_number:03d}",
            "camera_id": "cam_tracking_regression_01",
            "timestamp_utc": timestamp_utc,
            "frame_path": f"media/tracking/regression/frame_{frame_number:06d}.jpg",
            "frame_number": frame_number,
            "source_type": "file",
            "camera_profile": CameraProfile(
                camera_id="cam_tracking_regression_01",
                source_type=SourceType.file,
                resolution_w=640,
                resolution_h=360,
            ).model_dump(mode="json"),
        }
    )


def _candidate(
    timestamp_utc: str,
    *,
    vehicle_x: int,
    plate_text: str,
    color: str = "silver",
    make: str = "ford",
    model: str = "fusion",
) -> InferenceCandidate:
    return InferenceCandidate.model_validate(
        {
            "frame_id": f"cand_{timestamp_utc}",
            "camera_id": "cam_tracking_regression_01",
            "timestamp_utc": timestamp_utc,
            "vehicle_detections": [
                {
                    "bbox": {"x": vehicle_x, "y": 155, "w": 130, "h": 78},
                    "confidence": 0.92,
                    "class_label": "car",
                }
            ],
            "plate_detections": [
                {
                    "bbox": {"x": vehicle_x + 38, "y": 203, "w": 46, "h": 14},
                    "confidence": 0.94,
                    "vehicle_index": 0,
                }
            ],
            "ocr_candidates": [
                {"text": plate_text, "confidence": 0.95},
            ],
            "attribute_predictions": [
                AttributePredictions(
                    color=color,
                    color_confidence=0.91,
                    make=make,
                    make_confidence=0.88,
                    model=model,
                    model_confidence=0.82,
                ).model_dump(mode="json", by_alias=True)
            ],
            "model_versions": ModelVersions(
                vehicle_detector="fixture_vehicle",
                plate_detector="fixture_plate",
                ocr="fixture_ocr",
                classifier="fixture_attr",
            ).model_dump(mode="json"),
            "processing_latency_ms": 7.5,
        }
    )


def _empty_candidate(timestamp_utc: str) -> InferenceCandidate:
    return InferenceCandidate.model_validate(
        {
            "frame_id": f"cand_empty_{timestamp_utc}",
            "camera_id": "cam_tracking_regression_01",
            "timestamp_utc": timestamp_utc,
            "vehicle_detections": [],
            "plate_detections": [],
            "ocr_candidates": [],
            "attribute_predictions": [],
            "model_versions": ModelVersions().model_dump(mode="json"),
            "processing_latency_ms": 4.0,
        }
    )


def _tracking_service() -> TrackingService:
    pipeline = load_pipeline_config(REPO_ROOT / "configs" / "pipelines" / "default-edge.yaml")
    pipeline.tracking.min_hits_to_confirm = 2
    pipeline.tracking.max_lost_frames = 0
    pipeline.fusion.min_ocr_candidates_for_promotion = 1
    return TrackingService(pipeline)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_duplicate_suppression_suppresses_quick_repeat_pass():
    service = _tracking_service()
    finalized = []

    finalized.extend(service.ingest(_frame(1, "2026-03-24T18:40:00Z"), _candidate("2026-03-24T18:40:00Z", vehicle_x=180, plate_text="5DUP111")))
    finalized.extend(service.ingest(_frame(2, "2026-03-24T18:40:01Z"), _candidate("2026-03-24T18:40:01Z", vehicle_x=195, plate_text="5DUP111")))
    finalized.extend(service.ingest(_frame(3, "2026-03-24T18:40:02Z"), _empty_candidate("2026-03-24T18:40:02Z")))

    finalized.extend(service.ingest(_frame(4, "2026-03-24T18:40:05Z"), _candidate("2026-03-24T18:40:05Z", vehicle_x=182, plate_text="5DUP111")))
    finalized.extend(service.ingest(_frame(5, "2026-03-24T18:40:06Z"), _candidate("2026-03-24T18:40:06Z", vehicle_x=197, plate_text="5DUP111")))
    finalized.extend(service.ingest(_frame(6, "2026-03-24T18:40:07Z"), _empty_candidate("2026-03-24T18:40:07Z")))

    assert len(finalized) == 1
    assert finalized[0].best_plate_candidate is not None
    assert finalized[0].best_plate_candidate.text == "5DUP111"
    assert service.suppressed_duplicates == 1


def test_duplicate_suppression_allows_repeat_after_window():
    service = _tracking_service()
    finalized = []

    finalized.extend(service.ingest(_frame(1, "2026-03-24T18:41:00Z"), _candidate("2026-03-24T18:41:00Z", vehicle_x=180, plate_text="6LATE66", color="black", make="chevrolet", model="malibu")))
    finalized.extend(service.ingest(_frame(2, "2026-03-24T18:41:01Z"), _candidate("2026-03-24T18:41:01Z", vehicle_x=195, plate_text="6LATE66", color="black", make="chevrolet", model="malibu")))
    finalized.extend(service.ingest(_frame(3, "2026-03-24T18:41:02Z"), _empty_candidate("2026-03-24T18:41:02Z")))

    finalized.extend(service.ingest(_frame(4, "2026-03-24T18:41:18Z"), _candidate("2026-03-24T18:41:18Z", vehicle_x=182, plate_text="6LATE66", color="black", make="chevrolet", model="malibu")))
    finalized.extend(service.ingest(_frame(5, "2026-03-24T18:41:19Z"), _candidate("2026-03-24T18:41:19Z", vehicle_x=197, plate_text="6LATE66", color="black", make="chevrolet", model="malibu")))
    finalized.extend(service.ingest(_frame(6, "2026-03-24T18:41:20Z"), _empty_candidate("2026-03-24T18:41:20Z")))

    assert len(finalized) == 2
    assert [item.best_plate_candidate.text for item in finalized if item.best_plate_candidate is not None] == ["6LATE66", "6LATE66"]
    assert service.suppressed_duplicates == 0


def test_benchmark_tracking_strategies_reports_expected_regression_behavior():
    report = benchmark_tracking_strategies(generated_at_utc="2026-03-24T23:30:00Z")

    assert report.recommended_algorithm.value == "byte_tracker"
    assert report.algorithms["byte_tracker"].total_score == 72.0
    assert report.algorithms["deep_sort"].total_score == 72.0
    assert report.algorithms["sort"].total_score == 4.0

    crowded_byte = report.algorithms["byte_tracker"].scenarios["crowded_crossing"]
    crowded_sort = report.algorithms["sort"].scenarios["crowded_crossing"]
    motion_byte = report.algorithms["byte_tracker"].scenarios["camera_motion_drift"]
    motion_sort = report.algorithms["sort"].scenarios["camera_motion_drift"]
    repeat_byte = report.algorithms["byte_tracker"].scenarios["repeat_pass_duplicate_window"]

    assert crowded_byte.plate_exact_matches == 2
    assert crowded_byte.identity_switches == 0
    assert crowded_sort.plate_exact_matches == 1
    assert crowded_sort.identity_switches == 2
    assert motion_byte.finalized_detections == 1
    assert motion_byte.identity_switches == 0
    assert motion_sort.finalized_detections == 0
    assert motion_sort.identity_switches == 4
    assert repeat_byte.suppressed_duplicates == 1


def test_generate_tracking_evidence_writes_report(tmp_path):
    output_root = tmp_path / "tracking-fixtures"
    result = _run_script(
        "scripts/generate_tracking_evidence.py",
        "--output-root",
        str(output_root),
        "--overwrite",
    )

    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads(
        (output_root / "reports" / "tracking-strategy-benchmark.json").read_text(encoding="utf-8")
    )
    assert report["generated_at_utc"] == "2026-03-24T23:30:00Z"
    assert report["recommended_algorithm"] == "byte_tracker"
    assert report["algorithms"]["byte_tracker"]["scenarios"]["crowded_crossing"]["plate_exact_matches"] == 2
    assert report["algorithms"]["sort"]["scenarios"]["camera_motion_drift"]["identity_switches"] == 4
