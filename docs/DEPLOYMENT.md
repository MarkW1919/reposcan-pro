# DEPLOYMENT.md

RepoScan Pro is designed for local development on a workstation and deployment on edge GPU hardware such as Jetson Orin-class systems or equivalent.

## Local Development Baseline

- Python 3.11
- Node 24 / npm 11
- Docker Compose for Postgres/PostGIS and Redis
- local media, artifacts, and data directories outside version control

## Edge Deployment Goals

- deterministic service startup
- watchdog-friendly process model
- camera reconnect resilience
- persistent local queues and storage
- runtime visibility through health and logging surfaces

## Packaging Direction

- PyTorch for model development
- ONNX for portable runtime packaging
- TensorRT where hardware support and validation justify it
- promoted runtime bundles should be self-contained, use config-dir-relative paths, and include per-stage manifests plus hash validation before deployment handoff
- TensorRT bundles should also record engine compatibility metadata so deployment review can confirm CUDA, TensorRT, precision, and target device assumptions
- separate service packaging so ingest, inference, storage, and sync can recover independently

## Operational Requirements

- restart safely after power loss or process failure
- preserve local detections during remote outages
- avoid uncontrolled external dependencies on the mission-critical path
- support rollback-safe model or service promotion
- enforce media retention and react to low-storage conditions before writes start failing
- support operator-friendly evidence export for local handoff

## Storage Lifecycle

Use the deployment profile to drive storage maintenance and evidence export behavior:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_storage_maintenance.py --deployment-config .\configs\deployments\local-dev.yaml --json
.\.venv\Scripts\python.exe .\scripts\export_detection_package.py --detection-id det_20260320_010001 --deployment-config .\configs\deployments\local-dev.yaml --json
```

The storage lifecycle now uses:

- `media_retention` for category-specific pruning windows
- `storage_pressure` for warning and minimum free-space thresholds
- `.tmp` and `.bak` recovery files for the JSON-backed metadata store

## Metadata Backend

Deployment profiles now choose the storage metadata backend explicitly:

- local-dev keeps `metadata_backend: json` so the no-hardware demo path stays lightweight
- edge-style profiles can use `metadata_backend: postgres`

When using the Postgres backend, initialize the schema with:

```powershell
.\.venv\Scripts\python.exe .\scripts\bootstrap_postgres_storage.py --deployment-config .\configs\deployments\jetson-orin-edge.yaml
```

The Postgres adapter expects `psycopg` support in the environment, which is declared in the repo's `postgres` optional dependency group.

## Remote Sync And Alert Delivery

Deployment profiles can also describe optional outbound delivery integrations:

- `remote_sync` controls detection replay to an upstream HTTP endpoint
- `alert_delivery` controls optional webhook fan-out for alerts beyond the local UI

The current edge-style profile uses HTTP placeholder endpoints for this transport shape:

- `http://127.0.0.1:8081/sync/detections`
- `http://127.0.0.1:8081/alerts/webhook`

Refresh the repo-tracked evidence for these integrations with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_sync_remote_evidence.py --output-root .\services\sync\fixtures --overwrite
```

## Runtime Bundle Validation

Before an external promoted bundle is treated as deployment-ready, validate it against the intended deployment profile:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_edge_runtime_bundle.py `
  --model-config C:\artifacts\models\promoted\bundle-20260322\promoted-tensorrt.yaml `
  --deployment-config .\configs\deployments\jetson-orin-edge.yaml
```

This catches mismatches between the promoted bundle and the deployment target, including:

- backend expectations such as TensorRT on Jetson Orin
- config-dir-relative bundle requirements
- target runtime identifiers
- CUDA version, TensorRT version, and device compute capability expectations when the deployment profile requires them

After a bundle passes deployment validation and benchmark review, register it into an external release registry and move the deployment channel pointer rather than hand-tracking "current" bundles in notes or folder names. This keeps rollback to the previous accepted bundle explicit and audit-friendly.

## Related Documents

- [Requirements](REQUIREMENTS.md)
- [Inference](INFERENCE.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
- [Model Releases](MODEL_RELEASES.md)
- [Decisions](DECISIONS.md)
