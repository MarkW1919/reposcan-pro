# API_CONTRACTS.md

This document defines the canonical API contract direction for detections, alerts, search, and local-first persistence behavior.

## Contract Principles

- preserve local-first semantics
- keep API payloads explicit and typed
- include provenance and confidence where operator review matters
- avoid hiding uncertainty in OCR or classification results

## Detection Record Schema

| Field | Type | Notes |
| --- | --- | --- |
| `detection_id` | string | Stable unique identifier for the detection event |
| `timestamp_utc` | string | UTC timestamp in ISO 8601 form |
| `camera_id` | string | Logical camera identifier |
| `gps_latitude` | number or null | Latitude when available |
| `gps_longitude` | number or null | Longitude when available |
| `plate_text` | string or null | Best promoted OCR read |
| `plate_confidence` | number or null | Confidence for the best promoted read |
| `plate_candidates` | array | Alternate OCR candidates with confidence |
| `vehicle_bbox` | object | Vehicle bounding box in source-frame coordinates |
| `plate_bbox` | object or null | Plate bounding box in source-frame coordinates |
| `vehicle_color` | string or null | Promoted color label |
| `vehicle_color_confidence` | number or null | Confidence for color label |
| `vehicle_make` | string or null | Promoted make label |
| `vehicle_make_confidence` | number or null | Confidence for make label |
| `vehicle_model` | string or null | Promoted model label |
| `vehicle_model_confidence` | number or null | Confidence for model label |
| `optional_vehicle_year` | string or null | Year prediction when enabled |
| `optional_year_confidence` | number or null | Confidence for year prediction |
| `tracker_id` | string or null | Tracker association across frames |
| `image_path` | string | Local path or object reference to frame image |
| `plate_crop_path` | string or null | Local path to the best plate crop |
| `source_video_path` | string or null | Local reference to source snippet or file |
| `frame_number` | integer | Source frame index when available |
| `local_only_flag` | boolean | True until sync policy clears it |
| `sync_status` | string | Pending, synced, failed, or skipped |

## Canonical Versioning

The canonical external API surface is versioned under:

- `/api/v1`

Compatibility aliases without the version prefix may remain enabled for local clients, but new integrations should treat `/api/v1` as authoritative.

Use:

- `GET /api/v1/version`

to discover the active package version, API version, canonical prefix, and whether auth and rate limiting are enabled.

## Current API Surface

- `GET /api/v1/health` for service health and dependency summaries
- `GET /api/v1/dashboard/overview` for the operator summary surface
- `GET /api/v1/detections` for detection retrieval
- `GET /api/v1/detections/{id}` for full detection detail
- `GET /api/v1/detections/{id}/frame` and `GET /api/v1/detections/{id}/plate-crop` for evidence media
- `GET /api/v1/search/detections` for plate, date, camera, GPS-region, vehicle-attribute, and related alert-state filtering
- `GET /api/v1/search/alerts` for alert-state and joined detection-attribute filtering
- `POST /api/v1/reviews/{id}` and `GET /api/v1/reviews/{id}` for operator review workflows
- `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`, and `PUT /api/v1/alerts/{id}` for alert lifecycle management
- `GET /api/v1/hotlists`, `POST /api/v1/hotlists`, and `PUT /api/v1/hotlists/{id}` for hotlist management
- `GET /api/v1/demo/runtime` and `POST /api/v1/demo/runs` for app-driven headless ingest control
- `GET /api/v1/audit/events` for audit visibility over secured searches and operator mutations

## Auth, Audit, And Hardening

- authentication can be enabled per deployment profile
- authorization is role-based at the API boundary
- operator-visible mutations and secured search actions are audit logged
- request throttling and security headers are deployment-configurable
- trusted hosts and OpenAPI exposure are deployment-configurable

## Local-First Semantics

- successful detections are stored locally before sync is attempted
- review state changes are durable locally
- sync failures update `sync_status` but do not delete the local record

## Example Detection Payload

```json
{
  "detection_id": "det_20260319_000001",
  "timestamp_utc": "2026-03-19T22:10:00Z",
  "camera_id": "cam_north_gate_01",
  "gps_latitude": 34.12345,
  "gps_longitude": -118.12345,
  "plate_text": "8ABC123",
  "plate_confidence": 0.93,
  "plate_candidates": [
    {"text": "8ABC123", "confidence": 0.93},
    {"text": "8A8C123", "confidence": 0.41}
  ],
  "vehicle_bbox": {"x": 412, "y": 220, "w": 301, "h": 184},
  "plate_bbox": {"x": 518, "y": 338, "w": 86, "h": 28},
  "vehicle_color": "white",
  "vehicle_color_confidence": 0.88,
  "vehicle_make": "toyota",
  "vehicle_make_confidence": 0.67,
  "vehicle_model": "camry",
  "vehicle_model_confidence": 0.54,
  "optional_vehicle_year": null,
  "optional_year_confidence": null,
  "tracker_id": "trk_2048",
  "image_path": "media/frames/cam_north_gate_01/frame_000542.jpg",
  "plate_crop_path": "media/crops/cam_north_gate_01/det_20260319_000001.jpg",
  "source_video_path": "media/snippets/cam_north_gate_01/snippet_000542.mp4",
  "frame_number": 542,
  "local_only_flag": true,
  "sync_status": "pending"
}
```

## Related Documents

- [Architecture](ARCHITECTURE.md)
- [API Integration Guide](API_INTEGRATION_GUIDE.md)
- [UI Workflows](UI_WORKFLOWS.md)
- [Requirements](REQUIREMENTS.md)
