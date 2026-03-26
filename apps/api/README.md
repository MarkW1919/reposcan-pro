# API App

Host the external control and query surface for RepoScan Pro.

Current integrated slice:
- FastAPI app factory in `src/reposcan_api/app.py`
- ASGI entrypoint in `src/reposcan_api/main.py`
- canonical versioned API surface under `/api/v1`, with optional unversioned compatibility aliases
- health endpoint at `GET /api/v1/health`
- version endpoint at `GET /api/v1/version`
- dashboard overview endpoint at `GET /api/v1/dashboard/overview` with recent popup activity for the operator UI
- read-only detection endpoints at `GET /api/v1/detections`, `GET /api/v1/detections/{id}`, `GET /api/v1/detections/{id}/frame`, and `GET /api/v1/detections/{id}/plate-crop`
- search endpoints at `GET /api/v1/search/detections` and `GET /api/v1/search/alerts`
- review endpoints at `POST /api/v1/reviews/{id}` and `GET /api/v1/reviews/{id}`
- alert endpoints at `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`, and `PUT /api/v1/alerts/{id}`
- hotlist endpoints at `GET /api/v1/hotlists`, `POST /api/v1/hotlists`, and `PUT /api/v1/hotlists/{id}`
- demo runtime endpoints at `GET /api/v1/demo/runtime` and `POST /api/v1/demo/runs` for app-driven headless ingest
- audit surface at `GET /api/v1/audit/events`
- deployment-configured auth, role checks, request throttling, and trusted-host/security-header hardening
- seeded development storage for a live local UI demo path

Design rules:
- remain decoupled from camera and inference internals
- depend on shared contracts and the storage service boundary
- keep versioned routes canonical as the external integration surface
- keep auth, audit, and alert/hotlist expansion additive to the storage-boundary foundation
