# API App

Host the external control and query surface for RepoScan Pro.

Current Phase 2 skeleton:
- FastAPI app factory in `src/reposcan_api/app.py`
- ASGI entrypoint in `src/reposcan_api/main.py`
- health endpoint at `GET /health`
- read-only detection endpoints at `GET /detections` and `GET /detections/{id}`
- review write primitive at `POST /reviews/{id}`

Design rules:
- remain decoupled from camera and inference internals
- depend on shared contracts and the storage service boundary
- keep auth and alert/hotlist expansion additive to this foundation
