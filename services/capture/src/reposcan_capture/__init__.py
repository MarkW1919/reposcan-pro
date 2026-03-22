"""RepoScan Pro capture service primitives."""

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
    "LiveFrameSource",
    "OpenCvImageGrabber",
    "RegisteredCamera",
    "RtspFrameSource",
    "StaticGpsProvider",
    "UsbFrameSource",
]
