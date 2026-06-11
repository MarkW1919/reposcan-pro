# BUILD_KICKOFF.md

This document is the implementation start signal for Claude Code.

## Authorization

As of March 20, 2026, the design layer for RepoScan Pro is accepted enough to begin implementation.

Implementation must stay inside the boundaries defined by:
- [CLAUDE.md](../CLAUDE.md)
- [Implementation Blueprint](IMPLEMENTATION_BLUEPRINT.md)
- [API Contracts](API_CONTRACTS.md)
- [Architecture](ARCHITECTURE.md)

## First Build Objective

Start with Phase 1 from `IMPLEMENTATION_BLUEPRINT.md`:
- shared schemas and typed contracts
- configuration formats and validation
- tests that lock the contract and config behavior

Do not start with model training, production OCR tuning, or UI polish.

## First Deliverables

Claude Code should produce the first working implementation slice with:
- `packages/contracts/src/` initialized with the core detection, alert, review, hotlist, and health schemas
- config examples and validation/loading rules for `configs/cameras`, `configs/models`, `configs/pipelines`, and `configs/deployments`
- contract-focused tests under `tests/contracts/`
- minimal documentation updates for how to use the new contract and config foundation

## Working Style

- Make the smallest viable set of changes that establishes the foundation cleanly
- Prefer explicit typing and validation over placeholder abstractions
- Keep ownership boundaries aligned with the implementation blueprint
- Stop and surface architecture conflicts before expanding scope

## Suggested Claude Code Prompt

```text
Read CLAUDE.md, docs/BUILD_KICKOFF.md, docs/IMPLEMENTATION_BLUEPRINT.md, and docs/API_CONTRACTS.md.

Begin implementation now.

Limit the first pass to Phase 1 foundations:
- shared contracts in packages/contracts/src
- config schemas, examples, and loaders under configs/
- tests that validate contract and config behavior

Do not build inference, OCR, tracking, or UI features yet unless they are strictly needed to support the contract or config foundation.

Make the smallest coherent implementation slice, keep the architecture boundaries intact, and explain any design conflict before proceeding beyond the blueprint.
```
