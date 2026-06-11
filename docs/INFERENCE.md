# INFERENCE.md

Inference is edge-first and local-first. Cloud services may augment analysis later, but they must not become a prerequisite for the primary operational path.

## Runtime Principles

- deterministic startup
- config-driven model loading
- graceful failure and restart behavior
- low-latency local processing
- temporal aggregation across frames when it improves read quality

## Planned Inference Flow

1. Acquire frame and camera metadata.
2. Apply preprocessing suitable for the scene and hardware profile.
3. Detect vehicles.
4. Detect plates in full-frame or vehicle crops, depending on configuration.
5. Crop, rectify, and normalize the best plate candidates.
6. Run OCR and preserve alternate candidates with confidence.
7. Run vehicle attribute classification when image quality allows.
8. Fuse confidence and pass enriched detections to tracking and storage.

## Runtime Contracts

- normalize model IO through shared contracts
- keep detector, OCR, classifier, and tracker replaceable
- record model version metadata with detections where practical
- protect throughput from blocking sync or UI work

## Current Repo Runtime State

- the repo ships a tracked ONNX runtime fixture stack for real backend-loaded no-hardware validation
- the repo also keeps a tracked builtin demo runtime stack as the fallback path when external runtime packages or exported models are intentionally not in use
- that stack can read per-frame `*.inference.json` sidecars to vary detections, OCR, and vehicle attributes during headless ingest
- the repo now also ships promoted ONNX and TensorRT fixture bundles under `ml/inference/fixtures/` for repeatable promotion and deployment validation
- Section 4 runtime evidence is tracked in [Inference Runtime Evidence](INFERENCE_RUNTIME_EVIDENCE.md)
- model-stack readiness should be checked with `scripts/validate_model_stack.py` before swapping runtime configs
- self-contained promoted ONNX bundles can be packaged with `scripts/package_promoted_onnx_bundle.py`
- exported per-stage ONNX artifacts can be assembled into a promoted bundle with `scripts/assemble_promoted_onnx_bundle.py`
- promoted external bundles should be checked with `scripts/validate_promoted_model_bundle.py` once per-stage manifests exist
- TensorRT promoted bundles now have a metadata contract for CUDA, TensorRT version, precision, and device capability, and the repo includes a contract-validation fixture bundle for deployment-profile checks
- deployment-target compatibility can be checked with `scripts/validate_edge_runtime_bundle.py`
- benchmark evidence for `long_range` and `low_light` subsets now exists for the promoted ONNX fixture bundle, but it remains runtime evidence rather than field-acceptance proof

## Failure Handling

- camera loss must not crash the full stack
- model load failure must surface clearly and degrade safely
- GPS failure should not block detection storage
- sync failure must not interrupt local recording

## Related Documents

- [Architecture](ARCHITECTURE.md)
- [Models](MODELS.md)
- [Inference Runtime Evidence](INFERENCE_RUNTIME_EVIDENCE.md)
- [Model Promotion Workflow](MODEL_PROMOTION_WORKFLOW.md)
- [Deployment](DEPLOYMENT.md)
- [API Contracts](API_CONTRACTS.md)
