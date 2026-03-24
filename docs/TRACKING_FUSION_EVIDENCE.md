# TRACKING_FUSION_EVIDENCE.md

This document records the repo-tracked evidence that closes the remaining Section 5 tracking-and-fusion checklist items.

These artifacts prove tracker-strategy comparison, crowded-scene identity continuity, aggressive camera-motion tolerance, and repeat-pass duplicate suppression behavior.
They do not claim full field acceptance, target-hardware validation, or moving-platform real-world signoff.

## Repo-Tracked Evidence

- tracking strategy benchmark report:
  - [services/tracking/fixtures/reports/tracking-strategy-benchmark.json](../services/tracking/fixtures/reports/tracking-strategy-benchmark.json)

## Current Baseline

From the repo-tracked benchmark report:

- recommended algorithm: `byte_tracker`
- `byte_tracker` total score: `72.0`
- `deep_sort` total score: `72.0`
- `sort` total score: `4.0`

Scenario highlights:

- `crowded_crossing`
  - `byte_tracker`: `2/2` exact plate matches, `0` identity switches
  - `deep_sort`: `2/2` exact plate matches, `0` identity switches
  - `sort`: `1/2` exact plate matches, `2` identity switches
- `camera_motion_drift`
  - `byte_tracker`: `1` finalized detection, `0` identity switches
  - `deep_sort`: `1` finalized detection, `0` identity switches
  - `sort`: `0` finalized detections, `4` identity switches
- `repeat_pass_duplicate_window`
  - tuned duplicate suppression yields `1` stored detection and `1` suppressed duplicate
- `repeat_pass_after_window`
  - the same plate is stored again after the suppression window, producing `2` finalized detections and `0` suppressed duplicates

## Regenerate

Refresh the benchmark report with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_tracking_evidence.py --output-root .\services\tracking\fixtures --overwrite
```

## Scope Boundary

This evidence is enough to close Section 5 tracking-strategy evaluation and duplicate-suppression tuning.

It is not enough to close:

- Section 12 moving-vehicle and moving-platform acceptance runs
- Section 12 target-hardware acceptance runs
- Section 13 full-system field-readiness gates
