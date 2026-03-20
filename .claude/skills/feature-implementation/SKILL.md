# Feature Implementation Skill

## Purpose
Implement scoped features without breaking edge-first architecture or low-light performance goals.

## Inputs
- feature request
- impacted docs and contracts
- existing module boundaries

## Workflow
1. Inspect the relevant subsystem before editing.
2. Make the smallest change that satisfies the documented requirement.
3. Add logging, validation, and integration notes with the feature.
4. Keep cross-service contracts explicit when behavior changes.

## Output
- targeted implementation plan
- code changes in the natural module location
- test coverage or manual validation notes
