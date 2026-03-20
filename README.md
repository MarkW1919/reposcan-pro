# RepoScan Pro

RepoScan Pro is a fresh-build repository for a field-grade, edge-first vehicle intelligence platform optimized for long-range license plate capture, low-light resilience, and local-first operation.

## Current Repository Phase

This repository currently contains:
- the Claude operating contract and project memory
- specialist agent briefs and reusable skills
- the core design and requirements documents
- a monorepo scaffold for future API, UI, service, and ML code
- local bootstrap and validation scripts

This first pass intentionally defines architecture and working rules before implementation code is added.

## Mission Snapshot

RepoScan Pro is being designed to:
- detect vehicles at long range
- detect and isolate license plates
- perform OCR
- classify vehicle attributes
- survive low-light and no-light conditions
- run primary inference locally on edge hardware
- record detections with GPS, time, and camera metadata

The canonical mission and rules live in [CLAUDE.md](CLAUDE.md).

## Canonical Documents

- [Product](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Camera And Imaging](docs/CAMERA_AND_IMAGING.md)
- [Models](docs/MODELS.md)
- [Datasets](docs/DATASETS.md)
- [Training](docs/TRAINING.md)
- [Inference](docs/INFERENCE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [API Contracts](docs/API_CONTRACTS.md)
- [UI Workflows](docs/UI_WORKFLOWS.md)
- [Decisions](docs/DECISIONS.md)

## Repository Layout

```text
reposcan-pro/
├─ CLAUDE.md
├─ README.md
├─ docs/
├─ .claude/
│  ├─ settings.json
│  ├─ settings.local.json
│  ├─ agents/
│  └─ skills/
├─ apps/
│  ├─ api/
│  └─ ui/
├─ packages/
│  └─ contracts/
├─ services/
│  ├─ capture/
│  ├─ preprocessing/
│  ├─ inference/
│  ├─ tracking/
│  ├─ storage/
│  ├─ alerting/
│  └─ sync/
├─ ml/
│  ├─ training/
│  └─ inference/
├─ configs/
├─ infra/
├─ scripts/
└─ tests/
```

## Environment Baseline

- Python 3.11 via `py -3.11`
- Node 24 and npm 11
- Docker Compose for local Postgres/PostGIS and Redis
- Git with local milestone commits from day one

## Local Workflow

1. Run `powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1`
2. Review [CLAUDE.md](CLAUDE.md) and the documents under [docs](docs)
3. Run `powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1`
4. Start implementation only after the design layer is accepted

## Initial Claude Prompt

Use this prompt inside the repository before writing implementation code:

```text
Read CLAUDE.md and docs. Design the full system architecture and propose the initial repo structure without writing implementation code yet.
```

## Version Control And Artifact Policy

- Commit milestone changes locally as you progress.
- Do not commit datasets, model weights, local media, or generated runtime artifacts.
- Treat the existing prototype in the parent workspace as separate history and do not modify it from this repo.

