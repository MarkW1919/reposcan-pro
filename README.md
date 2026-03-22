# RepoScan Pro

RepoScan Pro is a fresh-build repository for a field-grade, edge-first vehicle intelligence platform optimized for long-range license plate capture, low-light resilience, and local-first operation.

## Current Repository Phase

This repository currently contains:
- shared contracts and config loaders
- local-first storage, alert, review, sync, and profiling service foundations
- FastAPI endpoints for health, detections, alerts, reviews, hotlists, dashboard overview, and popup activity
- a cab-first React operator UI with live popup activity, evidence preview, hotlist management, persistent alert response workflow, local review workflow, and app-driven demo ingest control when the API is available, plus local demo fallback when it is not
- a headless file-sequence ingest path that runs capture, low-light-oriented preprocessing, inference, tracking, alerting, and storage without camera hardware
- bootstrap, build, and validation scripts for the current integrated slice

The design-first scaffold has already been turned into a working implementation foundation.
The current focus is post-blueprint integration and demo readiness rather than returning to Phase 1 setup work.

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
- [Implementation Blueprint](docs/IMPLEMENTATION_BLUEPRINT.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Camera And Imaging](docs/CAMERA_AND_IMAGING.md)
- [Camera Deployment Workflow](docs/CAMERA_DEPLOYMENT_WORKFLOW.md)
- [Models](docs/MODELS.md)
- [Datasets](docs/DATASETS.md)
- [Training](docs/TRAINING.md)
- [Inference](docs/INFERENCE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [API Contracts](docs/API_CONTRACTS.md)
- [UI Workflows](docs/UI_WORKFLOWS.md)
- [Operations And Logging](docs/OPERATIONS_AND_LOGGING.md)
- [Project Status Checklist](docs/PROJECT_STATUS_CHECKLIST.md)
- [Decisions](docs/DECISIONS.md)

## Repository Layout

```text
reposcan-pro/
|-- CLAUDE.md
|-- README.md
|-- docs/
|-- .claude/
|   |-- settings.json
|   |-- settings.local.json
|   |-- agents/
|   `-- skills/
|-- apps/
|   |-- api/
|   `-- ui/
|-- packages/
|   `-- contracts/
|-- services/
|   |-- capture/
|   |-- preprocessing/
|   |-- inference/
|   |-- tracking/
|   |-- storage/
|   |-- alerting/
|   `-- sync/
|-- ml/
|   |-- training/
|   `-- inference/
|-- configs/
|-- infra/
|-- scripts/
`-- tests/
```

## Environment Baseline

- Python 3.11 via `py -3.11`
- Node 24 and npm 11
- Docker Compose for local Postgres/PostGIS and Redis
- Git with local milestone commits from day one

## Local Workflow

1. Run `powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1`
2. Open [RepoScan Pro.code-workspace](RepoScan Pro.code-workspace) in VS Code or run [Open RepoScan Pro Dev.cmd](Open RepoScan Pro Dev.cmd)
3. Review [CLAUDE.md](CLAUDE.md) and the documents under [docs](docs)
4. Run `powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1`
5. Start the API with `npm run api:dev`
6. Start the UI with `npm run ui:dev`
7. Use the manual demo checklist in [tests/manual/demo_vertical_slice.md](tests/manual/demo_vertical_slice.md)

## Headless Ingest Demo

Use the file-sequence runner to turn any folder of `.jpg` test frames into fresh detections and alerts that the live API and UI can serve immediately.
When preprocessing is enabled, the runner also writes inference-ready frame artifacts under `runtime/preprocessed` by default.

For a closer-to-deployable demo flow, start the API and UI, then launch the same ingest path from the `Quick Actions` panel inside `Recovery Alerts`.
The UI talks to the live API demo runtime endpoints, so new detections and alerts appear without opening another terminal, and the same panel can persist alert acknowledge, stand-down, and reopen actions during the demo.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_file_sequence_demo.py --frames-dir C:\path\to\frame-folder
```

The runner uses [configs/cameras/local-file-demo.yaml](configs/cameras/local-file-demo.yaml) by default, writes development metadata under `runtime/storage`, and writes preprocessing artifacts under `runtime/preprocessed` unless you override those paths.

## Desktop Launcher

To create the desktop launcher and double-click shortcut for this repo, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_launcher.ps1
```

That script creates:
- `RepoScan Pro Dev Home` on your desktop
- `RepoScan Pro Dev.lnk` on your desktop

Both point back to the repo-owned workspace and launcher files so the setup stays synced with the Git repository.

## Claude, Codex, And VS Code

- Claude Code integration lives in [CLAUDE.md](CLAUDE.md) and the files under [.claude](.claude)
- Codex is working directly against this Git-tracked repo
- VS Code integration lives in [.vscode](.vscode), [RepoScan Pro.code-workspace](RepoScan Pro.code-workspace), and [Open RepoScan Pro Dev.cmd](Open RepoScan Pro Dev.cmd)
- the older `Seen-It-First Dev Home` desktop launcher is a separate project and is not the entry point for this repo

## Claude Build Prompt

Use this prompt inside the repository to continue implementation from the current integrated state:

```text
Read CLAUDE.md, docs/IMPLEMENTATION_BLUEPRINT.md, docs/API_CONTRACTS.md, and the current repo state.

Continue the next implementation slice now.

Do not rebuild completed foundations. Prefer live integration, seeded demo readiness, operator workflow completion, test coverage, and manual field-test documentation.
```

## Version Control And Artifact Policy

- Commit milestone changes locally as you progress.
- Do not commit datasets, model weights, local media, or generated runtime artifacts.
- Treat the existing prototype in the parent workspace as separate history and do not modify it from this repo.
