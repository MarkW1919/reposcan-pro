# API_CONTRACTS.md

This document defines the initial contract direction for detections, alerts, and local-first persistence behavior.

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

## Initial API Surface

- `GET /health` for service health and dependency summaries
- `GET /detections` for filtered retrieval of detection records
- `GET /detections/{id}` for full detection detail
- `POST /reviews/{id}` for operator review or OCR correction actions
- `GET /alerts` for recent or active hotlist alerts
- `POST /hotlists` and `PUT /hotlists/{id}` for local hotlist management

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
- [UI Workflows](UI_WORKFLOWS.md)
- [Requirements](REQUIREMENTS.md)
