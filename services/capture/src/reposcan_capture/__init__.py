"""RepoScan Pro capture service primitives."""

from .gps import GpsProviderError, NmeaSerialGpsProvider, build_gps_provider, parse_nmea_sentence
from .service import CameraRegistry, CaptureService, RegisteredCamera
from .sources import (
    CaptureReconnectError,
    CaptureSourceError,
    CapturedFrame,
    CapturedImage,
    FileSequenceFrameSource,
    LiveFrameSource,
    OpenCvImageGrabber,
    RtspFrameSource,
    StaticGpsProvider,
    UsbFrameSource,
)

__all__ = [
    "CameraRegistry",
    "CaptureReconnectError",
    "CaptureSourceError",
    "CapturedFrame",
    "CapturedImage",
    "CaptureService",
    "FileSequenceFrameSource",
    "GpsProviderError",
    "LiveFrameSource",
    "NmeaSerialGpsProvider",
    "OpenCvImageGrabber",
    "RegisteredCamera",
    "RtspFrameSource",
    "StaticGpsProvider",
    "UsbFrameSource",
    "build_gps_provider",
    "parse_nmea_sentence",
]
