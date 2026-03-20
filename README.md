# RepoScan Pro

RepoScan Pro is a fresh-build repository for a field-grade, edge-first vehicle intelligence platform optimized for long-range license plate capture, low-light resilience, and local-first operation.

## Current Repository Phase

This repository currently contains:
- the Claude operating contract and project memory
- specialist agent briefs and reusable skills
- the core design and requirements documents
- a monorepo scaffold for future API, UI, service, and ML code
- local bootstrap and validation scripts

The design-first scaffold is complete enough to begin implementation as of March 20, 2026.
The first implementation pass should follow [Build Kickoff](docs/BUILD_KICKOFF.md) and remain inside Phase 1 of the [Implementation Blueprint](docs/IMPLEMENTATION_BLUEPRINT.md).

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
2. Open [RepoScan Pro.code-workspace](RepoScan Pro.code-workspace) in VS Code or run [Open RepoScan Pro Dev.cmd](Open RepoScan Pro Dev.cmd)
3. Review [CLAUDE.md](CLAUDE.md) and the documents under [docs](docs)
4. Run `powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1`
5. Begin implementation with [Build Kickoff](docs/BUILD_KICKOFF.md) and Phase 1 of the [Implementation Blueprint](docs/IMPLEMENTATION_BLUEPRINT.md)

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

Use this prompt inside the repository to begin the build:

```text
Read CLAUDE.md, docs/BUILD_KICKOFF.md, docs/IMPLEMENTATION_BLUEPRINT.md, and docs/API_CONTRACTS.md.

Begin implementation now.

Limit the first pass to Phase 1 foundations:
- shared contracts in packages/contracts/src
- config schemas, examples, and loaders under configs/
- tests that validate contract and config behavior

Do not build inference, OCR, tracking, or UI features yet unless they are strictly needed to support the contract or config foundation.
```

## Version Control And Artifact Policy

- Commit milestone changes locally as you progress.
- Do not commit datasets, model weights, local media, or generated runtime artifacts.
- Treat the existing prototype in the parent workspace as separate history and do not modify it from this repo.
