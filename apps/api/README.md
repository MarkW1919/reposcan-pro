# API App

Host the external control and query surface for RepoScan Pro.

Current integrated slice:
- FastAPI app factory in `src/reposcan_api/app.py`
- ASGI entrypoint in `src/reposcan_api/main.py`
- health endpoint at `GET /health`
- dashboard overview endpoint at `GET /dashboard/overview` with recent popup activity for the operator UI
- read-only detection endpoints at `GET /detections`, `GET /detections/{id}`, `GET /detections/{id}/frame`, and `GET /detections/{id}/plate-crop`
- review endpoints at `POST /reviews/{id}` and `GET /reviews/{id}`
- alert endpoints at `GET /alerts`, `GET /alerts/{id}`, and `PUT /alerts/{id}`
- hotlist endpoints at `GET /hotlists`, `POST /hotlists`, and `PUT /hotlists/{id}`
- demo runtime endpoints at `GET /demo/runtime` and `POST /demo/runs` for app-driven headless ingest
- seeded development storage for a live local UI demo path

Design rules:
- remain decoupled from camera and inference internals
- depend on shared contracts and the storage service boundary
- keep auth and alert/hotlist expansion additive to this foundation
