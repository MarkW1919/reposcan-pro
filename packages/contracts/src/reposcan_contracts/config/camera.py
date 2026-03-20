"""Camera configuration schema.

Loaded from configs/cameras/*.yaml by the capture service.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SourceType(str, Enum):
    rtsp = "rtsp"
    usb = "usb"
    file = "file"


class ColorMode(str, Enum):
    color = "color"
    ir = "ir"
    dual = "dual"


class ExposureMode(str, Enum):
    auto = "auto"
    manual = "manual"


class Orientation(str, Enum):
    fixed = "fixed"
    ptz = "ptz"


class SensorConfig(BaseModel):
    type: Optional[str] = Field(None, description="Sensor model identifier, e.g. 'sony_imx335'")
    resolution_w: Optional[int] = Field(None, gt=0)
    resolution_h: Optional[int] = Field(None, gt=0)
    fps: Optional[float] = Field(None, gt=0.0)
    bits_per_pixel: Optional[int] = Field(None, gt=0)
    color_mode: ColorMode = ColorMode.color


class OpticsConfig(BaseModel):
    focal_length_mm: Optional[float] = Field(None, gt=0.0)
    aperture_f: Optional[float] = Field(None, gt=0.0)
    ir_illuminator: bool = False
    ir_wavelength_nm: Optional[int] = Field(None, gt=0, description="IR LED wavelength, e.g. 850 or 940")


class ExposureConfig(BaseModel):
    mode: ExposureMode = ExposureMode.auto
    target_brightness: Optional[int] = Field(None, ge=0, le=255)
    shutter_speed_us: Optional[int] = Field(None, gt=0, description="Shutter speed in microseconds (manual only)")
    gain_db: Optional[float] = Field(None, description="Sensor gain in dB (manual only)")


class MountingConfig(BaseModel):
    height_m: Optional[float] = Field(None, gt=0.0, description="Mounting height in metres")
    angle_deg: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Tilt angle (negative = down)")
    orientation: Orientation = Orientation.fixed
    gps_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    gps_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    gps_accuracy_m: Optional[float] = Field(None, ge=0.0)


class CaptureConfig(BaseModel):
    target_fps: Optional[float] = Field(None, gt=0.0)
    reconnect_delay_s: float = Field(5.0, gt=0.0)
    max_reconnect_attempts: int = Field(0, ge=0, description="0 = unlimited")


class CameraConfig(BaseModel):
    """Complete camera configuration loaded from configs/cameras/*.yaml."""

    camera_id: str = Field(..., description="Stable logical camera identifier")
    display_name: Optional[str] = None
    source_type: SourceType
    stream_url: Optional[str] = Field(None, description="RTSP or HTTP stream URL (rtsp/file sources)")
    device_index: Optional[int] = Field(None, ge=0, description="USB device index (usb source)")
    sensor: SensorConfig = Field(default_factory=SensorConfig)
    optics: OpticsConfig = Field(default_factory=OpticsConfig)
    exposure: ExposureConfig = Field(default_factory=ExposureConfig)
    mounting: MountingConfig = Field(default_factory=MountingConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_source_binding(self) -> "CameraConfig":
        if self.source_type == SourceType.usb:
            if self.device_index is None:
                raise ValueError("device_index is required when source_type='usb'")
            if self.stream_url is not None:
                raise ValueError("stream_url must be omitted when source_type='usb'")
        else:
            if not self.stream_url:
                raise ValueError("stream_url is required when source_type is 'rtsp' or 'file'")
            if self.device_index is not None:
                raise ValueError("device_index must be omitted when source_type is 'rtsp' or 'file'")
        return self
