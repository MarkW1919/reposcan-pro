# MODEL_PROMOTION_WORKFLOW.md

RepoScan Pro keeps promoted model artifacts outside git, but the repo still needs a repeatable handoff shape so exported runtime bundles can be validated before deployment use.

## Goals

- keep promoted artifacts versioned outside the repository
- require a per-stage manifest for every runtime artifact
- validate the runtime config, artifact presence, and artifact hashes before deployment handoff
- keep promotion validation separate from field-accuracy claims

## Required Inputs

A promoted bundle should provide:

- a model-stack config shaped like [configs/models/promoted-onnx-template.yaml](../configs/models/promoted-onnx-template.yaml)
- for TensorRT engine bundles, use [configs/models/promoted-tensorrt-template.yaml](../configs/models/promoted-tensorrt-template.yaml)
- one artifact per stage
- one manifest per stage
- stable references to the source run, checkpoint, and dataset manifests when available

Each stage manifest should record at minimum:

- stage name
- model name
- backend
- artifact path
- artifact SHA-256
- export timestamp
- input width and height

Optional metadata should include the training run, checkpoint reference, export tool, opset, precision, target runtime, and dataset manifests whenever those details exist.

Promoted bundle configs should set `path_base: config_dir` so relative artifact and manifest paths stay valid when the bundle is moved outside the repository.

## TensorRT Manifest Metadata

TensorRT promoted bundles need more metadata than plain ONNX handoff because the engine is tied to a runtime stack and device profile. For TensorRT manifests, record:

- `target_runtime: tensorrt`
- `precision`
- `cuda_version`
- `tensorrt_version`
- `device_compute_capability`

Optional but recommended TensorRT metadata includes:

- `engine_profile`
- `workspace_megabytes`
- the original checkpoint or export command in `source_checkpoint_ref` and `export_tool`

## Package A Promoted ONNX Bundle

If you already have a runtime-ready ONNX stack, use the packaging helper to build a self-contained external bundle:

```powershell
.\.venv\Scripts\python.exe .\scripts\package_promoted_onnx_bundle.py `
  --source-model-config .\configs\models\local-onnx-runtime.yaml `
  --output-dir C:\artifacts\models\promoted\bundle-20260322 `
  --bundle-name lpr-bundle-20260322 `
  --source-run-id run_20260322_01 `
  --export-tool reposcan.package_promoted_onnx_bundle `
  --export-tool-version 0.1.0 `
  --opset-version 13 `
  --precision fp32 `
  --target-runtime onnxruntime
```

That command copies the ONNX artifacts into the output directory, writes `promoted-onnx.yaml`, writes per-stage manifests, and validates the packaged bundle before returning success.

## Generate Per-Stage Manifests

Use the repo helper to generate a manifest for each stage after an export is written:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_model_artifact_manifest.py `
  --model-config .\configs\models\promoted-onnx-template.yaml `
  --stage vehicle_detector `
  --output C:\artifacts\models\promoted\bundle-20260322\yolov8n-vehicle.manifest.json `
  --source-run-id run_20260322_01 `
  --source-checkpoint-ref yolov8n_vehicle_epoch42.pt `
  --dataset-manifest data\manifests\night-holdout.yaml `
  --export-tool torch.onnx.export `
  --export-tool-version 2.7.0 `
  --opset-version 17 `
  --precision fp16 `
  --target-runtime onnxruntime
```

Repeat that step for `plate_detector`, `ocr`, and `classifier`.

## Validate A Promoted Bundle

Before a deployment handoff, validate the full promoted bundle against its runtime config:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_promoted_model_bundle.py `
  --model-config C:\artifacts\models\promoted\bundle-20260322\promoted-onnx.yaml
```

This validation checks:

- the runtime model stack is internally loadable
- every configured stage has an artifact manifest path
- the manifest stage, model name, backend, artifact path, and input shape match the runtime config
- the artifact exists at the declared path
- the artifact SHA-256 matches the manifest
- relative bundle paths still resolve correctly when `path_base: config_dir` is used
- TensorRT bundles include the required engine compatibility metadata

Then validate the promoted bundle against the target deployment profile:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_edge_runtime_bundle.py `
  --model-config C:\artifacts\models\promoted\bundle-20260322\promoted-tensorrt.yaml `
  --deployment-config .\configs\deployments\jetson-orin-edge.yaml
```

This deployment-level check verifies that bundle metadata matches the intended target environment rather than just checking the bundle in isolation.

After bundle and deployment validation, use the promoted-bundle benchmark harness to collect exact-match and character-accuracy metrics across tagged subsets such as `long_range` and `low_light`.

## What This Does Not Prove

This workflow does not by itself prove:

- long-range accuracy
- low-light accuracy
- TensorRT readiness
- real TensorRT engine loadability on target hardware
- edge latency suitability
- field deployment approval

Those are separate acceptance gates and remain tracked in [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md).

## Related Documents

- [Models](MODELS.md)
- [Training](TRAINING.md)
- [Inference](INFERENCE.md)
- [Deployment](DEPLOYMENT.md)
- [Promoted Model Benchmarks](PROMOTED_MODEL_BENCHMARKS.md)
- [Decisions](DECISIONS.md)
