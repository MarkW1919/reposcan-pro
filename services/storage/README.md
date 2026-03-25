# Storage Service

Own local-first persistence for metadata, crops, media references, and review state.

Design rule:
- loss of internet connectivity must not block recording detections

Current capabilities:
- media layout helper for `media/frames`, `media/crops`, `media/snippets`, and `media/exports`
- repository boundary for detections, reviews, alerts, and hotlists
- in-memory repository for tests and local wiring
- JSON-backed metadata persistence with atomic writes plus backup-based recovery on restart
- deployment-selectable Postgres/PostGIS metadata repository
- deployment-aware retention sweeps and storage-pressure checks
- evidence export packaging for operator handoff

Useful commands:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_storage_maintenance.py --deployment-config .\configs\deployments\local-dev.yaml --json
.\.venv\Scripts\python.exe .\scripts\export_detection_package.py --detection-id det_20260320_010001 --json
.\.venv\Scripts\python.exe .\scripts\bootstrap_postgres_storage.py --deployment-config .\configs\deployments\jetson-orin-edge.yaml
```
