# ML Inference

Reserve runtime adapters, model registries, and export integration code for edge deployment.

Planned responsibilities:
- ONNX and TensorRT model packaging
- runtime compatibility checks
- confidence and metadata normalization

Current tracked assets:
- `fixtures/onnx-runtime/` contains committed ONNX fixture models used to validate backend-loaded inference wiring in the repo
- `fixtures/promoted-onnx-runtime/` contains the repo-tracked promoted ONNX fixture bundle used for Section 4 runtime evidence
- `fixtures/promoted-tensorrt-runtime/` contains the repo-tracked TensorRT contract-validation fixture bundle used for Jetson deployment-profile checks
- `fixtures/runtime-benchmark-holdout/` contains the approved internal image fixture set used for Section 4 benchmark plumbing
- `fixtures/reports/` contains the generated qualification, benchmark, and deployment-validation evidence reports for those fixture assets
- `..\..\scripts\generate_onnx_runtime_fixture_models.py` regenerates those fixture models when the output schema changes
- `..\..\scripts\generate_inference_runtime_evidence.py` refreshes the promoted fixture bundles, benchmark images, and evidence reports
- `..\..\scripts\generate_model_artifact_manifest.py` and `..\..\scripts\validate_promoted_model_bundle.py` support promoted-bundle handoff for external runtime artifacts
- `..\..\scripts\assemble_promoted_onnx_bundle.py` assembles a promoted ONNX bundle from exported per-stage ONNX artifacts
- `..\..\scripts\package_promoted_onnx_bundle.py` packages a runtime-ready ONNX stack into a self-contained external promoted bundle
- `..\..\configs\models\promoted-tensorrt-template.yaml` documents the expected external TensorRT engine bundle shape and required manifest metadata
- `..\..\scripts\validate_edge_runtime_bundle.py` checks a promoted bundle against a deployment profile such as `jetson-orin-edge`
- `..\..\scripts\benchmark_promoted_bundle.py` benchmarks a promoted bundle against a tagged frame manifest
