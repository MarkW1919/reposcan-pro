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

## Related Documents

- [Requirements](REQUIREMENTS.md)
- [Inference](INFERENCE.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
- [Decisions](DECISIONS.md)
