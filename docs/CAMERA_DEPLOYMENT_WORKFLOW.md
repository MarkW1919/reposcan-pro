# CAMERA_DEPLOYMENT_WORKFLOW.md

This document defines the repeatable workflow for registering deployed cameras and validating their mounting quality before a field run.

It does not replace the later field-validation requirement to actually capture and review the required long-range and low-light scenes. It defines the process the team should follow when that hardware is available.

## 1. Camera Registration Workflow

Use this workflow for each camera attached to a rig, trailer, or validation laptop.

1. Create or copy a camera config in `configs/cameras/`
2. Assign a stable `camera_id` that matches the intended mounting location
3. Set `source_type` correctly:
   - `rtsp` for network streams
   - `usb` for direct device capture
   - `file` only for deterministic test sequences
4. Fill in the source binding:
   - `stream_url` for RTSP
   - `device_index` for USB
5. Record sensor, optics, exposure, and mounting metadata as accurately as possible
6. Keep `enabled: false` until the config is validated and physically confirmed
7. Validate the registry with:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_camera_registry.py
```

8. Confirm the script output lists the new camera with the expected source binding
9. After physical confirmation, set `enabled: true`

## 2. Camera Naming Guidance

- prefer location-stable IDs such as `cam_north_gate_01`, `cam_bed_left_01`, or `cam_cab_usb_01`
- do not encode temporary IP addresses into the `camera_id`
- keep display names operator-friendly
- reserve source bindings for the actual stream URL or device index

## 3. Mounting Validation Workflow

Run this checklist any time a camera is installed, repositioned, or moved to another rig.

1. Confirm the mount is mechanically tight and does not drift during idle vibration
2. Confirm the target lane or parking geometry keeps the plate inside a useful pixel envelope
3. Confirm the angle of incidence does not create excessive retroreflective bloom
4. Confirm headlights and IR illumination do not wash out the plate region
5. Confirm the field of view is narrow enough for usable plate evidence, not just scene coverage
6. Confirm motion blur is controlled at the expected vehicle and truck movement speeds
7. Record the final mounting height, tilt, and orientation back into the camera config

## 4. Repeatable Drive-And-Scene Checks

Repeat these checks for every production-intended mounting position:

1. stationary target at expected standoff distance
2. slow rolling target crossing the frame
3. moving truck with stationary target
4. oncoming headlight exposure stress
5. dark vehicle against low-contrast background
6. IR-assisted scene if the rig uses IR illumination

## 5. Evidence Review Expectations

For each mounting position, save example frames that answer:

- is the plate large enough to be readable at the intended range
- is the plate still readable under motion
- does the mount introduce vibration blur or rolling-shutter artifacts
- do headlights, reflective plates, or IR hotspots destroy useful detail
- is the current exposure strategy helping or hurting the read

## 6. Current Software Support

The current repo now supports:

- camera config validation for RTSP, USB, and file-backed sources
- registry loading from a directory of camera configs
- local registry validation through `scripts/validate_camera_registry.py`
- RTSP and USB source adapters through the capture service with reconnect handling
- NMEA serial live GPS ingest wiring through camera config for deployed rigs that expose GPS over a serial device

The current repo does not yet complete the hardware-only acceptance work:

- captured and reviewed long-range acceptance scenes
- captured and reviewed low-light / no-light acceptance scenes

When the deployment rig arrives, run the capture campaign from [FIELD_CAPTURE_KIT.md](FIELD_CAPTURE_KIT.md). That pack carries the authoritative scene list, rig checklist, per-shot protocol, and handoff path for the acceptance harness.

## Related Documents

- [Camera And Imaging](CAMERA_AND_IMAGING.md)
- [Field Capture Kit](FIELD_CAPTURE_KIT.md)
- [Requirements](REQUIREMENTS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
