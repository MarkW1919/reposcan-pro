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
    NmeaSerialGpsProvider,
    RtspFrameSource,
    UsbFrameSource,
    build_gps_provider,
    parse_nmea_sentence,
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


class _FakeLineReader:
    def __init__(self, lines: list[str]) -> None:
        self._lines = deque(lines)
        self.closed = False

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.popleft()

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


def test_parse_nmea_sentence_supports_rmc_and_gga():
    rmc = parse_nmea_sentence("$GPRMC,123519,A,3407.3800,N,11827.3600,W,022.4,084.4,230394,003.1,W*6A")
    gga = parse_nmea_sentence("$GPGGA,123520,3407.4400,N,11827.4200,W,1,08,0.9,545.4,M,46.9,M,,*47")

    assert rmc is not None
    assert rmc.latitude == pytest.approx(34.123, rel=1e-4)
    assert rmc.longitude == pytest.approx(-118.456, rel=1e-4)
    assert gga is not None
    assert gga.latitude == pytest.approx(34.124, rel=1e-4)
    assert gga.longitude == pytest.approx(-118.457, rel=1e-4)


def test_build_gps_provider_from_camera_config_reads_nmea_sentences():
    camera = _camera_config(
        "usb",
        gps={
            "provider": "nmea_serial",
            "serial_port": "COM7",
            "baud_rate": 9600,
            "timeout_s": 0.1,
            "max_snapshot_age_s": 2.0,
        },
    )
    provider = build_gps_provider(
        camera,
        line_reader_factory=lambda *_: _FakeLineReader(
            [
                "$GPRMC,123519,A,3407.3800,N,11827.3600,W,022.4,084.4,230394,003.1,W*6A\n",
            ]
        ),
    )

    snapshot = provider.current_snapshot()

    assert snapshot is not None
    assert snapshot.latitude == pytest.approx(34.123, rel=1e-4)
    assert snapshot.longitude == pytest.approx(-118.456, rel=1e-4)
    provider.close()


def test_nmea_serial_provider_returns_cached_snapshot_when_no_new_line():
    provider = NmeaSerialGpsProvider(
        serial_port="COM7",
        timeout_s=0.1,
        max_snapshot_age_s=5.0,
        line_reader_factory=lambda *_: _FakeLineReader(
            [
                "$GPRMC,123519,A,3407.3800,N,11827.3600,W,022.4,084.4,230394,003.1,W*6A\n",
                "",
            ]
        ),
    )

    first = provider.current_snapshot()
    second = provider.current_snapshot()

    assert first is not None
    assert second is not None
    assert second.latitude == pytest.approx(first.latitude)
    assert second.longitude == pytest.approx(first.longitude)
    provider.close()


def test_rtsp_frame_source_auto_wires_live_gps_provider_from_camera_config(tmp_path):
    camera = _camera_config(
        "rtsp",
        capture={"reconnect_delay_s": 0.01, "max_reconnect_attempts": 1},
        gps={
            "provider": "nmea_serial",
            "serial_port": "COM7",
            "baud_rate": 9600,
            "timeout_s": 0.1,
            "max_snapshot_age_s": 2.0,
        },
    )

    source = RtspFrameSource(
        camera,
        output_root=tmp_path / "frames",
        gps_line_reader_factory=lambda *_: _FakeLineReader(
            [
                "$GPRMC,123519,A,3407.3800,N,11827.3600,W,022.4,084.4,230394,003.1,W*6A\n",
            ]
        ),
        max_frames=1,
        grabber_factory=lambda _: _FakeGrabber(
            [
                _captured_image(color=(24, 24, 24), timestamp_utc="2026-03-21T11:00:00Z"),
            ]
        ),
    )

    frames = list(source)

    assert len(frames) == 1
    assert frames[0].gps_snapshot is not None
    assert frames[0].gps_snapshot.latitude == pytest.approx(34.123, rel=1e-4)


def test_live_frame_source_drops_failed_gps_provider_without_blocking_capture(tmp_path):
    camera = _camera_config(
        "rtsp",
        gps={
            "provider": "nmea_serial",
            "serial_port": "COM7",
        },
    )

    def _broken_line_reader(*_args):
        raise RuntimeError("serial unavailable")

    source = RtspFrameSource(
        camera,
        output_root=tmp_path / "frames",
        gps_line_reader_factory=_broken_line_reader,
        max_frames=1,
        grabber_factory=lambda _: _FakeGrabber(
            [
                _captured_image(color=(24, 24, 24), timestamp_utc="2026-03-21T11:00:00Z"),
            ]
        ),
    )

    frames = list(source)

    assert len(frames) == 1
    assert frames[0].gps_snapshot is None


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
