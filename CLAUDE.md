# CLAUDE.md

## Project
RepoScan Pro (Fresh Build)

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
- Minimal changes over broad rewrites
- Always justify model choices
- Always consider imaging physics
- Always consider edge deployment

## Critical mindset
If the plate is not readable due to physics (distance, blur, light), no model will fix it.
Always evaluate signal quality before proposing AI changes.

