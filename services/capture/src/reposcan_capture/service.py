"""Capture service skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from reposcan_contracts.config.camera import CameraConfig
from reposcan_contracts.config.loader import load_camera_config
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, GpsSnapshot, SourceType

from .sources import CapturedFrame


def _camera_source_type(value: str) -> SourceType:
    return SourceType(value)


@dataclass(frozen=True)
class RegisteredCamera:
    camera_id: str
    display_name: str | None
    source_type: str
    enabled: bool
    binding: str
    gps_binding: str | None = None


class CameraRegistry:
    def __init__(self, cameras: dict[str, CameraConfig]) -> None:
        self._cameras = cameras

    @classmethod
    def from_files(cls, config_paths: Iterable[str | Path]) -> "CameraRegistry":
        cameras: dict[str, CameraConfig] = {}
        for path in config_paths:
            config = load_camera_config(path)
            if config.camera_id in cameras:
                raise ValueError(f"Duplicate camera_id '{config.camera_id}' in registry")
            cameras[config.camera_id] = config
        return cls(cameras)

    @classmethod
    def from_directory(
        cls,
        config_dir: str | Path,
        *,
        pattern: str = "*.yaml",
    ) -> "CameraRegistry":
        root = Path(config_dir)
        if not root.exists():
            raise FileNotFoundError(f"Camera config directory '{root}' does not exist")

        paths = sorted(path for path in root.glob(pattern) if path.is_file())
        if not paths:
            raise ValueError(f"No camera config files matched '{pattern}' in '{root}'")
        return cls.from_files(paths)

    def get(self, camera_id: str) -> CameraConfig:
        try:
            return self._cameras[camera_id]
        except KeyError as exc:
            raise KeyError(f"Unknown camera_id '{camera_id}'") from exc

    def list_camera_ids(self) -> list[str]:
        return sorted(self._cameras.keys())

    def list_cameras(self, *, enabled_only: bool = False) -> list[CameraConfig]:
        cameras = sorted(self._cameras.values(), key=lambda camera: camera.camera_id)
        if enabled_only:
            cameras = [camera for camera in cameras if camera.enabled]
        return cameras

    def enabled_camera_ids(self) -> list[str]:
        return [camera.camera_id for camera in self.list_cameras(enabled_only=True)]

    def registrations(self) -> list[RegisteredCamera]:
        registrations: list[RegisteredCamera] = []
        for camera in self.list_cameras():
            binding = camera.stream_url if camera.stream_url is not None else f"device:{camera.device_index}"
            gps_binding = None
            if camera.gps.provider.value == "nmea_serial" and camera.gps.serial_port:
                gps_binding = f"{camera.gps.provider.value}:{camera.gps.serial_port}"
            registrations.append(
                RegisteredCamera(
                    camera_id=camera.camera_id,
                    display_name=camera.display_name,
                    source_type=camera.source_type.value,
                    enabled=camera.enabled,
                    binding=binding,
                    gps_binding=gps_binding,
                )
            )
        return registrations


class CaptureService:
    """Normalize camera metadata and wrap acquired frames in FrameEnvelope."""

    def build_camera_profile(self, camera: CameraConfig) -> CameraProfile:
        return CameraProfile(
            camera_id=camera.camera_id,
            display_name=camera.display_name,
            source_type=_camera_source_type(camera.source_type.value),
            sensor_type=camera.sensor.type,
            resolution_w=camera.sensor.resolution_w,
            resolution_h=camera.sensor.resolution_h,
            fps=camera.sensor.fps,
            ir_mode=(camera.sensor.color_mode.value != "color") or camera.optics.ir_illuminator,
            gps_latitude=camera.mounting.gps_latitude,
            gps_longitude=camera.mounting.gps_longitude,
        )

    def _default_gps_snapshot(self, camera: CameraConfig) -> GpsSnapshot | None:
        if camera.mounting.gps_latitude is None or camera.mounting.gps_longitude is None:
            return None
        return GpsSnapshot(
            latitude=camera.mounting.gps_latitude,
            longitude=camera.mounting.gps_longitude,
            accuracy_m=camera.mounting.gps_accuracy_m,
        )

    def capture_frame(
        self,
        camera: CameraConfig,
        captured_frame: CapturedFrame,
    ) -> FrameEnvelope:
        return FrameEnvelope(
            frame_id=f"frm_{uuid4().hex[:16]}",
            camera_id=camera.camera_id,
            timestamp_utc=captured_frame.timestamp_utc,
            frame_path=str(captured_frame.frame_path),
            frame_number=captured_frame.frame_number,
            source_type=_camera_source_type(camera.source_type.value),
            camera_profile=self.build_camera_profile(camera),
            gps_snapshot=captured_frame.gps_snapshot or self._default_gps_snapshot(camera),
            sequence_id=captured_frame.sequence_id,
        )

    def capture_sequence(
        self,
        camera: CameraConfig,
        source: Iterable[CapturedFrame],
    ) -> list[FrameEnvelope]:
        return [self.capture_frame(camera, captured_frame) for captured_frame in source]
