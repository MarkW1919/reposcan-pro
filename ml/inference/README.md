# ML Inference

Reserve runtime adapters, model registries, and export integration code for edge deployment.

Planned responsibilities:
- ONNX and TensorRT model packaging
- runtime compatibility checks
- confidence and metadata normalization

Current tracked assets:
- `fixtures/onnx-runtime/` contains committed ONNX fixture models used to validate backend-loaded inference wiring in the repo
- `..\..\scripts\generate_onnx_runtime_fixture_models.py` regenerates those fixture models when the output schema changes
