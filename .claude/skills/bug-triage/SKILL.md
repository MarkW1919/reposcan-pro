# Bug Triage Skill

## Purpose
Investigate failures in detection, OCR, storage, sync, or operator workflows and narrow them to actionable causes.

## Inputs
- bug report or field symptom
- logs, sample media, and recent changes when available

## Workflow
1. Reproduce or restate the failure in operational terms.
2. Determine whether the root cause is imaging, model behavior, runtime, storage, or contract mismatch.
3. Capture the smallest reliable reproduction path.
4. Recommend the safest fix path with validation steps.

## Output
- probable root cause
- impacted subsystem
- validation plan for the fix

