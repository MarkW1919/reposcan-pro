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
