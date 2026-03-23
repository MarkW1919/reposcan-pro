# Inference Service

Orchestrate vehicle detection, plate detection, OCR, and vehicle attribute classification.

Design rule:
- load models from configuration so detectors and OCR engines remain replaceable

Current integrated slice:
- config-driven inference service that loads model and pipeline configs
- replaceable stub adapter bundle for vehicle, plate, OCR, and attribute stages
- tracked builtin runtime adapters that load repo-owned artifact manifests for the no-hardware demo path
- tracked ONNX runtime adapters that execute committed fixture models through `onnxruntime`
- frame-to-candidate workflow helper for the local capture-to-inference path using prepared-frame artifacts when preprocessing is active
- headless file-sequence runtime that chains preprocessing, inference, tracking, alerting, and storage for local end-to-end validation
- frame sidecar support via `*.inference.json` files so demo sequences can vary detections, OCR, and attributes per frame
- model-stack validation helpers and a CLI script for runtime readiness checks
- promoted-bundle manifest helpers and validation scripts for external artifact handoff
- promoted ONNX bundle packaging helpers for self-contained external handoff directories
- TensorRT promoted-bundle validation rules for required engine compatibility metadata
- deployment-target validation helpers that compare promoted bundles against deployment-profile runtime requirements
- promoted-bundle benchmark helpers for tagged long-range / low-light evaluation scaffolds
- inference profiling helpers for latency benchmarking and deployment recommendations
