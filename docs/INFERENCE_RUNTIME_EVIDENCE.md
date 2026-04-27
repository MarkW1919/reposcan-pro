# INFERENCE_RUNTIME_EVIDENCE.md

This document records the repo-tracked evidence that closes the remaining Section 4 inference-runtime checklist items.

These artifacts prove runtime bundle assembly, promotion validation, deployment-profile validation, and tagged benchmark reporting.
They do not claim field acceptance, target-hardware execution, or representative night / long-range accuracy in the real world.

## Repo-Tracked Evidence

- promoted ONNX fixture bundle:
  - [ml/inference/fixtures/promoted-onnx-runtime/promoted-onnx.yaml](../ml/inference/fixtures/promoted-onnx-runtime/promoted-onnx.yaml)
- promoted TensorRT contract fixture bundle:
  - [ml/inference/fixtures/promoted-tensorrt-runtime/promoted-tensorrt.yaml](../ml/inference/fixtures/promoted-tensorrt-runtime/promoted-tensorrt.yaml)
- qualified runtime benchmark holdout manifest:
  - [configs/datasets/runtime-benchmark-qualified-holdout.yaml](../configs/datasets/runtime-benchmark-qualified-holdout.yaml)
- holdout qualification report:
  - [ml/inference/fixtures/reports/runtime-benchmark-qualified-holdout.qualification.json](../ml/inference/fixtures/reports/runtime-benchmark-qualified-holdout.qualification.json)
- promoted ONNX benchmark report:
  - [ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json](../ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json)
- promoted ONNX local-dev deployment validation:
  - [ml/inference/fixtures/reports/promoted-onnx-runtime.local-dev.validation.json](../ml/inference/fixtures/reports/promoted-onnx-runtime.local-dev.validation.json)
- promoted TensorRT Jetson validation:
  - [ml/inference/fixtures/reports/promoted-tensorrt-runtime.jetson-orin.validation.json](../ml/inference/fixtures/reports/promoted-tensorrt-runtime.jetson-orin.validation.json)

## Current Baseline

From the repo-tracked benchmark report:

- overall exact match: `0.9`
- overall character accuracy: `0.986`
- `long_range` exact match: `1.0`
- `low_light` exact match: `0.857`
- deployment readiness in the benchmark report: `true`

From the repo-tracked qualification report:

- total assets: `10`
- benchmark-ready assets: `10`
- `long_range` assets: `5`
- `low_light` assets: `7`
- qualification result: `true`

From the deployment validation reports:

- promoted ONNX fixture bundle validates cleanly for `local-dev`
- promoted TensorRT contract bundle validates cleanly for `jetson-orin-nano-super`

## Regenerate

Refresh the fixture bundles, images, and evidence reports with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_inference_runtime_evidence.py --output-root .\ml\inference\fixtures --overwrite
```

## Scope Boundary

This evidence is enough to close Section 4 runtime validation and benchmark existence.

It is not enough to close:

- Section 10 field-relevant evaluation reports
- Section 11 target-edge packaging finalization
- Section 12 target-hardware acceptance runs
- Section 13 full-system field-readiness gates
