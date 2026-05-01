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

## Alert Record Schema

| Field | Type | Notes |
| --- | --- | --- |
| `alert_id` | string | Stable unique identifier for the alert event |
| `detection_id` | string | Detection that triggered the alert |
| `hotlist_entry_id` | string | Matched hotlist identifier |
| `timestamp_utc` | string | UTC timestamp in ISO 8601 form |
| `camera_id` | string | Logical camera identifier |
| `matched_plate_text` | string | Plate text used for the match |
| `match_confidence` | number | Confidence for the alert match |
| `match_type` | string | `exact` or `normalized` |
| `hotlist_label` | string or null | Human-readable label from the hotlist |
| `notes` | string or null | Operator or workflow notes |
| `response_operator_id` | string or null | Operator who updated the alert |
| `response_notes` | string or null | Most recent response note |
| `updated_at_utc` | string or null | Most recent update time |
| `status` | string | `active`, `acknowledged`, or `dismissed` |
| `gps_latitude` | number or null | Latitude when available |
| `gps_longitude` | number or null | Longitude when available |

## Recovery Account Schema

| Field | Type | Notes |
| --- | --- | --- |
| `entry_id` | string | Stable unique identifier for the recovery account |
| `plate_text` | string or null | Plate watch value used for live alert matching when present |
| `vin` | string or null | VIN stored for repo-order intake and manual locate workflows |
| `vehicle_year` | string or null | Target vehicle year |
| `vehicle_make` | string or null | Target vehicle make |
| `vehicle_model` | string or null | Target vehicle model |
| `vehicle_color` | string or null | Target vehicle color |
| `address_label` | string or null | Short label for the target address or lot |
| `address_line1` | string or null | Primary target address line |
| `address_line2` | string or null | Secondary target address line |
| `address_city` | string or null | Target address city |
| `address_state` | string or null | Target address state |
| `address_postal_code` | string or null | Target address postal code |
| `address_latitude` | number or null | Optional geocoded latitude |
| `address_longitude` | number or null | Optional geocoded longitude |
| `label` | string or null | Repo label, lender label, or case identifier |
| `notes` | string or null | Recovery instructions and operator notes |
| `active` | boolean | Whether the account is actively being tracked |
| `created_at_utc` | string | UTC creation timestamp |
| `updated_at_utc` | string | UTC update timestamp |

Current alerting behavior:

- live automatic alerting remains plate-driven
- accounts without `plate_text` are valid for repo intake, address attachment, and manual locate workflows
- VIN and vehicle-profile fields are persisted so the UI and backend share the same account context even before a confirmed plate exists

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
- `GET /api/v1/search/addresses` for operator destination lookup, biased local address search, and route-entry suggestions
- `GET /api/v1/search/reverse-address` for resolving the current unit latitude and longitude into a compact operator-readable address
- `POST /api/v1/reviews/{id}` and `GET /api/v1/reviews/{id}` for operator review workflows
- `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`, and `PUT /api/v1/alerts/{id}` for alert lifecycle management
- `GET /api/v1/hotlists`, `POST /api/v1/hotlists`, and `PUT /api/v1/hotlists/{id}` for recovery account management
- `GET /api/v1/follow-ups`, `GET /api/v1/follow-ups/{id}`, `POST /api/v1/follow-ups`, and `PUT /api/v1/follow-ups/{id}` for follow-up workflows
- `GET /api/v1/assignments`, `GET /api/v1/assignments/{id}`, `POST /api/v1/assignments`, and `PUT /api/v1/assignments/{id}` for dispatch assignment workflows
- `GET /api/v1/demo/runtime` and `POST /api/v1/demo/runs` for app-driven headless ingest control
- `GET /api/v1/audit/events` for audit visibility over secured searches and operator mutations

## Auth, Audit, And Hardening

- authentication can be enabled per deployment profile
- authorization is role-based at the API boundary
- operator-visible mutations and secured search actions are audit logged
- request throttling and security headers are deployment-configurable
- trusted hosts and OpenAPI exposure are deployment-configurable

Address lookup specifics:

- `GET /api/v1/search/addresses` accepts `q`, `limit`, and optional `bias_latitude` plus `bias_longitude`
- `GET /api/v1/search/reverse-address` accepts `latitude` and `longitude`
- both address lookup routes use the same secured search boundary and emit audit actions
- reverse-address lookup is intentionally limited to compact street-address context and provider provenance; it does not restore the previously removed advanced local enrichment flow

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
