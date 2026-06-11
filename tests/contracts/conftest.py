"""Shared fixtures for contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

# Absolute path to the repo root — used to resolve config file paths in tests.
REPO_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def configs_dir(repo_root: Path) -> Path:
    return repo_root / "configs"


# --- Minimal valid detection payload matching API_CONTRACTS.md example ---

@pytest.fixture
def minimal_detection_data() -> dict:
    return {
        "detection_id": "det_20260319_000001",
        "timestamp_utc": "2026-03-19T22:10:00Z",
        "camera_id": "cam_north_gate_01",
        "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
        "image_path": "media/frames/cam_north_gate_01/frame_000542.jpg",
        "frame_number": 542,
    }


@pytest.fixture
def full_detection_data() -> dict:
    return {
        "detection_id": "det_20260319_000001",
        "timestamp_utc": "2026-03-19T22:10:00Z",
        "camera_id": "cam_north_gate_01",
        "gps_latitude": 34.12345,
        "gps_longitude": -118.12345,
        "plate_text": "8ABC123",
        "plate_confidence": 0.93,
        "plate_candidates": [
            {"text": "8ABC123", "confidence": 0.93},
            {"text": "8A8C123", "confidence": 0.41},
        ],
        "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
        "plate_bbox": {"x": 518, "y": 338, "w": 86, "h": 28},
        "vehicle_color": "white",
        "vehicle_color_confidence": 0.88,
        "vehicle_make": "toyota",
        "vehicle_make_confidence": 0.67,
        "vehicle_model": "camry",
        "vehicle_model_confidence": 0.54,
        "optional_vehicle_year": None,
        "optional_year_confidence": None,
        "tracker_id": "trk_2048",
        "image_path": "media/frames/cam_north_gate_01/frame_000542.jpg",
        "plate_crop_path": "media/crops/cam_north_gate_01/det_20260319_000001.jpg",
        "source_video_path": "media/snippets/cam_north_gate_01/snippet_000542.mp4",
        "frame_number": 542,
        "local_only_flag": True,
        "sync_status": "pending",
    }
