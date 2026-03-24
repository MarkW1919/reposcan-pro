# FIELD_EVAL_QUALIFICATION.md

RepoScan Pro should not treat every `eval_holdout` manifest as automatically ready for regression use.

This document defines the current qualification gate for reviewed field-eval datasets.

## Purpose

The qualification gate answers:

- does this holdout have enough total assets to be useful?
- does it contain enough `long_range` examples?
- does it contain enough `low_light` examples?
- do those subsets span more than one capture session?
- do the assets carry the expected plate labels needed for exact-match and character-accuracy reporting?

## Current Gate

Use the CLI:

```powershell
.\.venv\Scripts\python.exe .\scripts\qualify_field_eval_dataset.py `
  --dataset-manifest C:\artifacts\data\manifests\oklahoma-field-eval.yaml `
  --verify-files `
  --report-output C:\artifacts\data\reports\oklahoma-field-eval-qualification.json
```

By default, the gate requires at least:

- `10` total assets
- `10` benchmark-ready assets with expected plate text
- `4` `long_range` assets across `2` capture sessions
- `4` `low_light` assets across `2` capture sessions

These are minimum regression-gate thresholds, not a claim that the holdout is fully representative for production.

## What The Report Contains

The qualification report captures:

- total assets
- benchmark-ready assets
- missing expected-plate-label count
- missing-file count when `--verify-files` is enabled
- subset counts for `long_range` and `low_light`
- subset capture-session coverage
- pass/fail issues with explicit threshold messages

## Why This Matters

Section 10 still requires dedicated night and long-range holdouts plus real evaluation reports. This gate keeps the repo honest by separating:

- a holdout manifest that merely exists
- a holdout manifest that is actually big enough and labeled enough to support regression use

## Related Documents

- [Datasets](DATASETS.md)
- [Training](TRAINING.md)
- [Promoted Model Benchmarks](PROMOTED_MODEL_BENCHMARKS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
