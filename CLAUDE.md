# CLAUDE.md

## Project
RepoScan Pro (Fresh Build)

## Current phase
As of March 20, 2026, the design layer is accepted and implementation is authorized.

Claude Code should begin the build now, using `docs/IMPLEMENTATION_BLUEPRINT.md` as the execution boundary and `docs/API_CONTRACTS.md` as the initial contract reference.

## Build kickoff order
Start with the first implementation slice only:
1. Define shared schemas and typed contracts in `packages/contracts`
2. Define config formats and validation for cameras, models, pipelines, and deployments under `configs/`
3. Add tests that lock those contracts and config rules
4. Only after Phase 1 is stable, begin the local storage and API skeleton described in the implementation blueprint

Do not jump ahead to full inference, OCR, tracking, or UI implementation before the contracts and configuration foundation is in place.

## Mission
Design and build a field-grade, edge-first AI system that:
- detects vehicles at long range
- detects license plates
- performs OCR
- classifies vehicles (color, make, model)
- operates reliably in extreme low-light / no-light conditions
- runs locally (edge-first)
- stores detections with GPS and timestamp

## Engineering priorities (strict order)
1. Long-range plate readability
2. Low-light / no-light performance
3. Stable real-time edge inference
4. OCR accuracy
5. Vehicle classification accuracy
6. Local-first storage and alerting

## System constraints
- No dependency on internet for core operation
- No cloud-only inference
- No demo-only optimizations
- No architecture drift without approval

## Architecture rules
- Modular design
- Replaceable model components
- Config-driven model loading
- Clear separation of:
  - capture
  - inference
  - storage
  - API
  - UI

## Required subsystems
- camera ingest
- preprocessing
- vehicle detection
- plate detection
- OCR
- classification
- tracking
- storage
- alerting
- API
- UI

## Claude responsibilities
- system architecture
- module boundaries
- integration planning
- code review
- performance validation
- protecting system integrity

## Codex responsibilities
- implementation
- training scripts
- dataset tooling
- repetitive code generation

## Operating rules
- Design before coding
- The design phase is complete enough to begin the implementation phases defined in `docs/IMPLEMENTATION_BLUEPRINT.md`
- Minimal changes over broad rewrites
- Always justify model choices
- Always consider imaging physics
- Always consider edge deployment
- When implementation reveals a design conflict, pause and resolve the conflict before widening scope

## Delivery expectations
- Build in small, working slices
- Add validation and tests with each new contract or config format
- Prefer foundations that unblock multiple services over isolated feature work
- Keep shared schemas in `packages/contracts` and service-specific logic inside the owning service
- Preserve local-first behavior from the start

## Critical mindset
If the plate is not readable due to physics (distance, blur, light), no model will fix it.
Always evaluate signal quality before proposing AI changes.
