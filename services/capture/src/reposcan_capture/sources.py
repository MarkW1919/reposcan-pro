"""Capture source primitives for camera and file-backed test ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Callable, Iterable, Iterator, Protocol

from PIL import Image

from reposcan_contracts.config.camera import CameraConfig, SourceType as CameraSourceType
from reposcan_contracts.frame import GpsSnapshot


def _parse_utc_timestamp(timestamp_utc: str) -> datetime:
    return datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CaptureSourceError(RuntimeError):
    """Raised when a live capture source cannot acquire the next frame."""


class CaptureReconnectError(CaptureSourceError):
    """Raised when reconnect attempts are exhausted for a live source."""


@dataclass(frozen=True)
class CapturedFrame:
    frame_path: Path
    timestamp_utc: str
    frame_number: int
    sequence_id: str | None = None
    gps_snapshot: GpsSnapshot | None = None


@dataclass(frozen=True)
class CapturedImage:
    image: Image.Image
    timestamp_utc: str | None = None
    gps_snapshot: GpsSnapshot | None = None


class ImageGrabber(Protocol):
    def open(self) -> None:
        ...

    def read(self) -> CapturedImage | None:
        ...

    def close(self) -> None:
        ...


class GpsProvider(Protocol):
    def current_snapshot(self) -> GpsSnapshot | None:
        ...


class StaticGpsProvider:
    def __init__(self, snapshot: GpsSnapshot | None) -> None:
        self._snapshot = snapshot

    def current_snapshot(self) -> GpsSnapshot | None:
        return self._snapshot


class FileSequenceFrameSource(Iterable[CapturedFrame]):
    """Deterministic file-backed frame source for local development and tests."""

    def __init__(
        self,
        frame_paths: list[Path],
        *,
        start_timestamp_utc: str,
        frame_interval_ms: float = 33.3,
        start_frame_number: int = 0,
        sequence_id: str | None = None,
        gps_snapshot: GpsSnapshot | None = None,
    ) -> None:
        if frame_interval_ms <= 0:
            raise ValueError("frame_interval_ms must be greater than zero")

        self.frame_paths = frame_paths
        self.start_timestamp_utc = start_timestamp_utc
        self.frame_interval_ms = frame_interval_ms
        self.start_frame_number = start_frame_number
        self.sequence_id = sequence_id
        self.gps_snapshot = gps_snapshot

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        glob_pattern: str = "*.jpg",
        start_timestamp_utc: str,
        frame_interval_ms: float = 33.3,
        start_frame_number: int = 0,
        sequence_id: str | None = None,
        gps_snapshot: GpsSnapshot | None = None,
    ) -> "FileSequenceFrameSource":
        root = Path(directory)
        frame_paths = sorted(path for path in root.glob(glob_pattern) if path.is_file())
        return cls(
            frame_paths,
            start_timestamp_utc=start_timestamp_utc,
            frame_interval_ms=frame_interval_ms,
            start_frame_number=start_frame_number,
            sequence_id=sequence_id,
            gps_snapshot=gps_snapshot,
        )

    def __iter__(self) -> Iterator[CapturedFrame]:
        start_time = _parse_utc_timestamp(self.start_timestamp_utc)
        delta = timedelta(milliseconds=self.frame_interval_ms)

        for index, frame_path in enumerate(self.frame_paths):
            timestamp_utc = _format_utc_timestamp(start_time + (delta * index))
            yield CapturedFrame(
                frame_path=frame_path,
                timestamp_utc=timestamp_utc,
                frame_number=self.start_frame_number + index,
                sequence_id=self.sequence_id,
                gps_snapshot=self.gps_snapshot,
            )


class OpenCvImageGrabber:
    """Optional OpenCV-backed grabber for RTSP and USB sources."""

    def __init__(self, source_binding: str | int) -> None:
        self._source_binding = source_binding
        self._capture = None

    def open(self) -> None:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise CaptureSourceError(
                "OpenCV is required for RTSP and USB capture sources but is not installed"
            ) from exc

        self._capture = cv2.VideoCapture(self._source_binding)
        if not self._capture.isOpened():
            self._capture.release()
            self._capture = None
            raise CaptureSourceError(f"Unable to open capture source '{self._source_binding}'")

    def read(self) -> CapturedImage | None:
        if self._capture is None:
            raise CaptureSourceError("Capture source is not open")

        success, frame = self._capture.read()
        if not success or frame is None:
            return None

        image = Image.fromarray(frame[:, :, ::-1])
        return CapturedImage(
            image=image,
            timestamp_utc=_format_utc_timestamp(datetime.now(timezone.utc)),
        )

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


def _default_grabber_factory(camera: CameraConfig) -> ImageGrabber:
    if camera.source_type == CameraSourceType.usb:
        if camera.device_index is None:
            raise CaptureSourceError("USB camera requires a device_index")
        return OpenCvImageGrabber(camera.device_index)

    if camera.stream_url is None:
        raise CaptureSourceError("RTSP camera requires a stream_url")
    return OpenCvImageGrabber(camera.stream_url)


class LiveFrameSource(Iterable[CapturedFrame]):
    """Live-source frame capture with reconnect handling and local evidence writes."""

    def __init__(
        self,
        camera: CameraConfig,
        *,
        output_root: str | Path,
        grabber_factory: Callable[[CameraConfig], ImageGrabber] | None = None,
        gps_provider: GpsProvider | None = None,
        start_frame_number: int = 0,
        sequence_id: str | None = None,
        max_frames: int | None = None,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        if start_frame_number < 0:
            raise ValueError("start_frame_number must be non-negative")
        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be greater than zero when provided")

        self.camera = camera
        self.output_root = Path(output_root)
        self.grabber_factory = grabber_factory or _default_grabber_factory
        self.gps_provider = gps_provider
        self.start_frame_number = start_frame_number
        self.sequence_id = sequence_id
        self.max_frames = max_frames
        self.sleep_fn = sleep_fn

    def _open_grabber(self) -> ImageGrabber:
        grabber = self.grabber_factory(self.camera)
        grabber.open()
        return grabber

    def _write_frame_image(self, frame_number: int, image: Image.Image) -> Path:
        frame_path = self.output_root / self.camera.camera_id / f"frame_{frame_number:06d}.jpg"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(frame_path, format="JPEG")
        return frame_path

    def _next_gps_snapshot(self, captured: CapturedImage) -> GpsSnapshot | None:
        if captured.gps_snapshot is not None:
            return captured.gps_snapshot
        if self.gps_provider is None:
            return None
        return self.gps_provider.current_snapshot()

    def _reconnect_or_raise(
        self,
        reconnect_attempts: int,
        reason: str,
    ) -> int:
        max_attempts = self.camera.capture.max_reconnect_attempts
        if max_attempts > 0 and reconnect_attempts >= max_attempts:
            raise CaptureReconnectError(
                f"Exceeded reconnect attempts for camera '{self.camera.camera_id}': {reason}"
            )
        self.sleep_fn(self.camera.capture.reconnect_delay_s)
        return reconnect_attempts + 1

    def __iter__(self) -> Iterator[CapturedFrame]:
        frames_emitted = 0
        frame_number = self.start_frame_number
        reconnect_attempts = 0
        grabber: ImageGrabber | None = None

        try:
            while self.max_frames is None or frames_emitted < self.max_frames:
                if grabber is None:
                    grabber = self._open_grabber()

                try:
                    captured = grabber.read()
                except CaptureSourceError as exc:
                    grabber.close()
                    grabber = None
                    reconnect_attempts = self._reconnect_or_raise(reconnect_attempts, str(exc))
                    continue

                if captured is None:
                    grabber.close()
                    grabber = None
                    reconnect_attempts = self._reconnect_or_raise(
                        reconnect_attempts,
                        "capture source returned no frame",
                    )
                    continue

                reconnect_attempts = 0
                frame_path = self._write_frame_image(frame_number, captured.image)
                yield CapturedFrame(
                    frame_path=frame_path,
                    timestamp_utc=captured.timestamp_utc or _format_utc_timestamp(datetime.now(timezone.utc)),
                    frame_number=frame_number,
                    sequence_id=self.sequence_id,
                    gps_snapshot=self._next_gps_snapshot(captured),
                )
                frame_number += 1
                frames_emitted += 1
        finally:
            if grabber is not None:
                grabber.close()


class RtspFrameSource(LiveFrameSource):
    def __init__(self, camera: CameraConfig, **kwargs: object) -> None:
        if camera.source_type != CameraSourceType.rtsp:
            raise ValueError("RtspFrameSource requires a camera config with source_type='rtsp'")
        super().__init__(camera, **kwargs)


class UsbFrameSource(LiveFrameSource):
    def __init__(self, camera: CameraConfig, **kwargs: object) -> None:
        if camera.source_type != CameraSourceType.usb:
            raise ValueError("UsbFrameSource requires a camera config with source_type='usb'")
        super().__init__(camera, **kwargs)
