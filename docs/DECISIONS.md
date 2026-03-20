# DECISIONS.md

This document records early accepted decisions for the fresh build.

## ADR-001 Fresh Repository Location

- Date: 2026-03-19
- Status: Accepted
- Decision: Create RepoScan Pro as a new repository under `C:\Users\mark\Documents\Playground\reposcan-pro`.
- Rationale: Preserve the earlier prototype untouched while allowing a clean architecture-first build.

## ADR-002 Claude-First Bootstrap

- Date: 2026-03-19
- Status: Accepted
- Decision: Establish `CLAUDE.md`, `.claude` config, agents, skills, and canonical docs before implementation code.
- Rationale: Architecture and operating rules need to be explicit before code generation begins.

## ADR-003 US-First Scope

- Date: 2026-03-19
- Status: Accepted
- Decision: Optimize V1 documents, OCR assumptions, and dataset strategy for US plate styles first.
- Rationale: Multi-region support is possible later, but V1 needs a coherent baseline for training and validation.

## ADR-004 Python 3.11 Baseline

- Date: 2026-03-19
- Status: Accepted
- Decision: Pin the project baseline to Python 3.11 instead of the machine's default Python 3.14.
- Rationale: The edge and ML ecosystem is more stable on Python 3.11 for current export and runtime tooling.

## ADR-005 Local-First Storage And Edge-First Inference

- Date: 2026-03-19
- Status: Accepted
- Decision: Core detection, OCR, storage, and alerting remain local-first, with sync treated as optional and asynchronous.
- Rationale: Mission-critical behavior cannot depend on internet availability.

## ADR-006 Canonical Architecture And Model Doc Names

- Date: 2026-03-19
- Status: Accepted
- Decision: Use `docs/ARCHITECTURE.md` and `docs/MODELS.md` as canonical document names.
- Rationale: These names match the newer starter spec and reduce ambiguity during the fresh build.

## ADR-007 Standard Default Branch

- Date: 2026-03-20
- Status: Accepted
- Decision: Publish and set `main` as the default branch for the GitHub repository, while keeping `codex/bootstrap` as the active working branch.
- Rationale: The repository should present a conventional default branch while preserving a clear implementation branch for ongoing work.

## ADR-008 Repo-Owned Editor Integration

- Date: 2026-03-20
- Status: Accepted
- Decision: Keep VS Code integration artifacts inside the repository rather than relying on a separate desktop-only workspace.
- Rationale: Editor setup for RepoScan Pro should be versioned, reviewable, and synced with the project rather than hidden in machine-local launcher folders.

## ADR-009 Reproducible Desktop Launcher

- Date: 2026-03-20
- Status: Accepted
- Decision: Generate desktop shortcuts for RepoScan Pro from a repo-owned script rather than hand-maintaining launcher files outside the repository.
- Rationale: The machine-local shortcut should remain reproducible while the source of truth stays versioned in Git.
