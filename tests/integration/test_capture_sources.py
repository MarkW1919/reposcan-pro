from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest
from PIL import Image

from reposcan_capture import (
    CameraRegistry,
    CaptureReconnectError,
    CaptureSourceError,
    CapturedImage,
    RtspFrameSource,
    UsbFrameSource,
)
from reposcan_contracts.config.camera import CameraConfig
from reposcan_contracts.frame import GpsSnapshot


class _StaticSequenceGpsProvider:
    def __init__(self, snapshots: list[GpsSnapshot | None]) -> None:
        self._snapshots = deque(snapshots)

    def current_snapshot(self) -> GpsSnapshot | None:
        if not self._snapshots:
            return None
        return self._snapshots.popleft()


class _FakeGrabber:
    def __init__(self, events: list[CapturedImage | Exception | None]) -> None:
        self._events = deque(events)
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def read(self) -> CapturedImage | None:
        if not self._events:
            return None
        event = self._events.popleft()
        if isinstance(event, Exception):
            raise event
        return event

    def close(self) -> None:
        self.closed = True


def _camera_config(source_type: str, **overrides: object) -> CameraConfig:
    base: dict[str, object] = {
        "camera_id": f"cam_{source_type}_01",
        "display_name": f"{source_type.upper()} camera",
        "source_type": source_type,
        "capture": {
            "reconnect_delay_s": 0.01,
            "max_reconnect_attempts": 2,
        },
    }
    if source_type == "usb":
        base["device_index"] = 0
    else:
        base["stream_url"] = "rtsp://127.0.0.1/stream"
    base.update(overrides)
    return CameraConfig.model_validate(base)


def _captured_image(*, color: tuple[int, int, int], timestamp_utc: str | None = None) -> CapturedImage:
    return CapturedImage(
        image=Image.new("RGB", (32, 24), color=color),
        timestamp_utc=timestamp_utc,
    )


def test_camera_registry_loads_directory_and_registration_summary(tmp_path):
    config_dir = tmp_path / "cameras"
    config_dir.mkdir()
    (config_dir / "north_gate.yaml").write_text(
        "\n".join(
            [
                "camera_id: cam_north_gate_01",
                "display_name: North Gate",
                "source_type: rtsp",
                "stream_url: rtsp://10.0.0.10/stream",
                "enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    (config_dir / "cab_usb.yaml").write_text(
        "\n".join(
            [
                "camera_id: cam_cab_usb_01",
                "display_name: Cab USB",
                "source_type: usb",
                "device_index: 1",
                "enabled: false",
            ]
        ),
        encoding="utf-8",
    )

    registry = CameraRegistry.from_directory(config_dir)

    assert registry.list_camera_ids() == ["cam_cab_usb_01", "cam_north_gate_01"]
    assert registry.enabled_camera_ids() == ["cam_north_gate_01"]
    registrations = registry.registrations()
    assert registrations[0].binding == "device:1"
    assert registrations[1].binding == "rtsp://10.0.0.10/stream"


def test_camera_registry_from_directory_rejects_missing_or_empty_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        CameraRegistry.from_directory(tmp_path / "missing")

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="No camera config files matched"):
        CameraRegistry.from_directory(empty_dir)


def test_rtsp_frame_source_writes_frames_and_applies_live_gps_provider(tmp_path):
    camera = _camera_config("rtsp", capture={"reconnect_delay_s": 0.01, "max_reconnect_attempts": 1})
    provider = _StaticSequenceGpsProvider(
        [
            GpsSnapshot(latitude=34.123, longitude=-118.456, accuracy_m=1.5),
            GpsSnapshot(latitude=34.124, longitude=-118.457, accuracy_m=1.4),
        ]
    )

    source = RtspFrameSource(
        camera,
        output_root=tmp_path / "frames",
        gps_provider=provider,
        max_frames=2,
        grabber_factory=lambda _: _FakeGrabber(
            [
                _captured_image(color=(24, 24, 24), timestamp_utc="2026-03-21T11:00:00Z"),
                _captured_image(color=(30, 30, 30), timestamp_utc="2026-03-21T11:00:01Z"),
            ]
        ),
    )

    frames = list(source)

    assert len(frames) == 2
    assert frames[0].frame_path.exists()
    assert frames[0].gps_snapshot is not None
    assert frames[0].gps_snapshot.latitude == pytest.approx(34.123)
    assert frames[1].gps_snapshot is not None
    assert frames[1].gps_snapshot.longitude == pytest.approx(-118.457)


def test_usb_frame_source_reconnects_after_transient_failure(tmp_path):
    camera = _camera_config("usb")
    sleep_calls: list[float] = []
    factories = deque(
        [
            _FakeGrabber([CaptureSourceError("temporary usb read failure")]),
            _FakeGrabber([_captured_image(color=(90, 90, 90), timestamp_utc="2026-03-21T11:05:00Z")]),
        ]
    )

    source = UsbFrameSource(
        camera,
        output_root=tmp_path / "frames",
        max_frames=1,
        sleep_fn=sleep_calls.append,
        grabber_factory=lambda _: factories.popleft(),
    )

    frames = list(source)

    assert len(frames) == 1
    assert frames[0].frame_path.exists()
    assert sleep_calls == [0.01]


def test_live_frame_source_raises_after_reconnect_budget_exhausted(tmp_path):
    camera = _camera_config("rtsp")
    sleep_calls: list[float] = []

    source = RtspFrameSource(
        camera,
        output_root=tmp_path / "frames",
        max_frames=1,
        sleep_fn=sleep_calls.append,
        grabber_factory=lambda _: _FakeGrabber([None]),
    )

    with pytest.raises(CaptureReconnectError):
        list(source)

    assert sleep_calls == [0.01, 0.01]
