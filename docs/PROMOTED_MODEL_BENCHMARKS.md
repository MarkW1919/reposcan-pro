# PROMOTED_MODEL_BENCHMARKS.md

This document defines the current benchmark scaffold for promoted runtime bundles.

It is intentionally a scaffold, not a claim that RepoScan Pro has already completed real long-range or low-light acceptance testing. The goal is to make those future evaluations repeatable and reviewable.

## What The Harness Does

- loads a promoted runtime bundle
- loads a tagged benchmark manifest
- runs inference frame by frame
- computes overall and per-tag metrics
- reports at least:
  - plate exact-match rate
  - character accuracy
  - vehicle color accuracy when labels are present
  - vehicle make accuracy when labels are present

## Current Tag Strategy

The scaffold recognizes arbitrary tags, but the most important near-term tags are:

- `long_range`
- `low_light`

Those tags let the report break out the two most important open Section 4 evaluation slices without changing the code every time new subsets are added.

## Example Usage

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_promoted_bundle.py `
  --model-config C:\artifacts\models\promoted\bundle-20260323\promoted-onnx.yaml `
  --benchmark-manifest .\configs\benchmarks\example-promoted-onnx-benchmark.yaml
```

## What This Proves Today

- the benchmark manifest shape is typed and loadable
- promoted ONNX bundles can be benchmarked locally
- reports can break out `long_range` and `low_light` subset metrics

## What This Does Not Prove Yet

- real field long-range accuracy
- real field low-light accuracy
- dataset representativeness
- target-hardware latency under benchmark load
- production acceptance readiness

Those remain open until the team runs this harness against true holdout datasets and promoted field models.

## Related Documents

- [Training](TRAINING.md)
- [Datasets](DATASETS.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
