# STORAGE_MEDIA_WORKFLOWS.md

This document records the current storage-lifecycle workflows that close the software-only Section 6 storage/media items.

These workflows prove retention enforcement, low-space response, evidence export packaging, and file-backed recovery behavior.
They now also include a deployment-selectable Postgres/PostGIS metadata backend.

## Current Capabilities

- deployment-selectable metadata backend:
  - `json` for local-dev
  - `postgres` for edge-style deployment profiles
- deployment-aware media retention sweeps using the active deployment profile
- free-space checks with `ok`, `warning`, and `critical` storage-pressure states
- evidence export packaging for a single detection, including manifest, reviews, alerts, hotlist context, and available media files
- JSON-backed metadata writes with `.tmp` and `.bak` recovery on restart
- Postgres schema bootstrap that enables PostGIS before creating metadata tables

## Postgres Backend

The repository now includes a real `PostgresStorageRepository` adapter while keeping `json` as the default local-dev backend.

Current profile defaults:

- `configs/deployments/local-dev.yaml` -> `metadata_backend: json`
- `configs/deployments/jetson-orin-edge.yaml` -> `metadata_backend: postgres`
- `configs/deployments/jetson-orin-nano-super.yaml` -> `metadata_backend: postgres`

When a deployment profile uses `metadata_backend: postgres`, initialize the metadata schema with:

```powershell
.\.venv\Scripts\python.exe .\scripts\bootstrap_postgres_storage.py `
  --deployment-config .\configs\deployments\jetson-orin-nano-super.yaml
```

The bootstrap path:

- connects through `infrastructure.postgres_url`
- requests `CREATE EXTENSION IF NOT EXISTS postgis`
- creates the storage metadata tables and indexes if they do not already exist

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

This is enough to close Section 6 storage/media.

It is not enough to close later deployment, acceptance, and full-system field-readiness gates.
