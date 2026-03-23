# DECISIONS.md

This document records accepted architectural and operational decisions for the fresh build.

Maintenance rule:
- add a new ADR whenever an implementation slice changes service boundaries, data flow, persistence strategy, operator workflow ownership, or deployment assumptions
- update the status and rationale if a later decision supersedes an earlier one
- prefer small, dated entries over retroactive rewrites so the reasoning trail stays reviewable

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

## ADR-010 Shared Contracts As Service Boundary

- Date: 2026-03-20
- Status: Accepted
- Decision: Keep typed schemas, config models, and inter-service contracts in `packages/contracts`, with runtime services depending on those contracts instead of defining parallel local payloads.
- Rationale: The fresh build needs one canonical schema surface so API, storage, capture, inference, and UI integration do not drift independently.

## ADR-011 JSON-Backed Local Metadata For Early Vertical Slices

- Date: 2026-03-20
- Status: Accepted
- Decision: Use local JSON-backed metadata persistence and filesystem media references for the current implementation slices before introducing the planned Postgres/PostGIS backend.
- Rationale: This preserves local-first behavior, keeps the no-hardware demo path simple, and allows operator workflow integration to progress before database infrastructure hardening.

## ADR-012 Headless File-Sequence Runtime Before Hardware Capture

- Date: 2026-03-20
- Status: Accepted
- Decision: Deliver an end-to-end file-sequence ingest runtime that chains capture, preprocessing, inference, tracking, alerting, and storage before camera hardware is attached.
- Rationale: The team needs a deterministic, Windows-friendly validation harness that exercises the real service boundaries and unblocks UI, alerting, and evidence workflows without waiting for live cameras.

## ADR-013 API-Owned Operator Mutations

- Date: 2026-03-20
- Status: Accepted
- Decision: Keep operator reviews, hotlist edits, alert lifecycle changes, and demo runtime control behind API endpoints instead of letting the UI mutate local storage or service internals directly.
- Rationale: Operator actions need a single audit-ready boundary and should remain compatible with later auth, sync, and multi-client growth.

## ADR-014 Detection-Scoped Media Endpoints

- Date: 2026-03-21
- Status: Accepted
- Decision: Expose evidence frames and plate crops through detection-scoped API endpoints rather than serving raw repository-relative file paths directly to the UI.
- Rationale: This keeps the browser client decoupled from local filesystem layout details and gives the API one place to enforce media existence, path resolution, and future auth controls.

## ADR-015 Dismissed Alerts Suppress Popup Activity

- Date: 2026-03-21
- Status: Accepted
- Decision: Once an alert is dismissed, suppress both its hotlist popup entry and the linked detection from the live popup activity stream.
- Rationale: A stand-down action should behave like a real operator suppression event; leaving the linked detection visible as a general popup would undermine alert lifecycle semantics in the live UI.

## ADR-016 Tracked Demo Runtime Separate From Exported Model Stacks

- Date: 2026-03-22
- Status: Accepted
- Decision: Keep a repo-tracked builtin model stack for the no-hardware demo path, and keep the exported ONNX/TensorRT stack definitions separate until real promoted artifacts exist.
- Rationale: The repo needs a self-contained inference runtime for integration demos and tests today, but it should not imply that placeholder exported model paths are already validated deployable assets.

## ADR-017 ONNX Fixture Runtime Before Promoted Field Models

- Date: 2026-03-22
- Status: Accepted
- Decision: Add a tracked ONNX runtime fixture stack to prove real backend-loaded inference execution before promoted field models and TensorRT exports are ready.
- Rationale: The repo needs to verify true runtime wiring for vehicle, plate, OCR, and attribute stages now, while still keeping accuracy, export promotion, and edge-benchmark claims separate.

## ADR-018 Promoted Bundles Require Per-Stage Artifact Manifests

- Date: 2026-03-22
- Status: Accepted
- Decision: Require promoted runtime bundles to provide one manifest per stage, and validate those manifests against the runtime config before deployment handoff.
- Rationale: Exported artifacts live outside git, so the repo needs a stable, reviewable contract for artifact identity, hash verification, and promotion metadata without pretending that placeholder paths alone are deployable proof.

## ADR-019 External Promoted Bundles Resolve Paths Relative To The Bundle Config

- Date: 2026-03-22
- Status: Accepted
- Decision: Support `path_base: config_dir` for model stacks so packaged promoted bundles can resolve artifact and manifest paths relative to the external bundle config instead of assuming the repository root.
- Rationale: A promoted bundle should remain valid after it is copied outside the repo; repo-root-relative paths are fine for tracked development configs but are too brittle for deployment handoff artifacts.

## ADR-020 TensorRT Promoted Bundles Require Engine Compatibility Metadata

- Date: 2026-03-22
- Status: Accepted
- Decision: Require promoted TensorRT engine manifests to record target runtime, precision, CUDA version, TensorRT version, and target device compute capability.
- Rationale: A TensorRT engine is tightly coupled to its runtime environment; external bundle review needs compatibility metadata even before true edge execution validation is available.

## ADR-021 Deployment Profiles Gate Promoted Bundle Compatibility

- Date: 2026-03-22
- Status: Accepted
- Decision: Validate promoted runtime bundles against deployment-profile runtime expectations before treating them as deployable-ready handoff artifacts.
- Rationale: Bundle-level validation is necessary but not sufficient; deployability also depends on matching the target backend, runtime, and edge-compatibility metadata defined by the deployment profile.

## ADR-022 Promoted Benchmarking Uses Tagged Frame Manifests

- Date: 2026-03-23
- Status: Accepted
- Decision: Benchmark promoted bundles with typed frame manifests that carry subset tags such as `long_range` and `low_light`.
- Rationale: The repo needs a repeatable way to compare promoted bundles against the specific scenarios that matter most without hardcoding benchmark subsets into the evaluator.

## ADR-023 Legacy Training Assets Enter RepoScan Through Typed Dataset Manifests

- Date: 2026-03-23
- Status: Accepted
- Decision: Reuse old Seen-It-First training assets only through typed RepoScan dataset manifests and review tooling rather than importing the old training/runtime code paths directly.
- Rationale: The legacy workspace contains useful warm-start datasets, staged raw captures, and synthetic OCR support data, but RepoScan Pro needs provenance review, split control, and artifact discipline that match the new repository boundaries.
