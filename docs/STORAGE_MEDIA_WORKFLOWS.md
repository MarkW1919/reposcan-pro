# STORAGE_MEDIA_WORKFLOWS.md

This document records the current storage-lifecycle workflows that close the software-only Section 6 storage/media items.

These workflows prove retention enforcement, low-space response, evidence export packaging, and file-backed recovery behavior.
They do not claim that the Postgres/PostGIS backend is complete yet.

## Current Capabilities

- deployment-aware media retention sweeps using the active deployment profile
- free-space checks with `ok`, `warning`, and `critical` storage-pressure states
- evidence export packaging for a single detection, including manifest, reviews, alerts, hotlist context, and available media files
- JSON-backed metadata writes with `.tmp` and `.bak` recovery on restart

## Storage Maintenance

Run retention enforcement and a storage-pressure check with:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_storage_maintenance.py `
  --deployment-config .\configs\deployments\local-dev.yaml `
  --metadata-root .\runtime\storage `
  --media-root .\media `
  --json
```

This reads:

- retention windows from `media_retention`
- warning and minimum free-space thresholds from `storage_pressure`

## Evidence Export

Package a detection for operator handoff with:

```powershell
.\.venv\Scripts\python.exe .\scripts\export_detection_package.py `
  --detection-id det_20260320_010001 `
  --deployment-config .\configs\deployments\local-dev.yaml `
  --metadata-root .\runtime\storage `
  --media-root .\media `
  --json
```

The export zip contains:

- `manifest.json`
- the detection record
- attached reviews
- related alerts
- referenced hotlist entries
- available frame, crop, and snippet media files when present

If storage pressure is already `critical`, export is blocked rather than risking a write failure.

## Recovery Behavior

The JSON-backed repository now writes through:

- `*.json.tmp` during the in-progress write
- `*.json.bak` as the last known good snapshot

On startup:

- if the primary file is valid, it is used
- if the primary file is missing or corrupt, the repository restores from `.tmp` or `.bak`
- if neither recovery file is usable, the repository falls back to an empty list for that store

## Scope Boundary

This is enough to close the software-only storage lifecycle items in Section 6.

It is not enough to close:

- the Postgres/PostGIS metadata backend item
- later deployment, acceptance, and full-system field-readiness gates
