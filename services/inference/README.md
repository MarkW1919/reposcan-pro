# Inference Service

Orchestrate vehicle detection, plate detection, OCR, and vehicle attribute classification.

Design rule:
- load models from configuration so detectors and OCR engines remain replaceable

Current Phase 3 skeleton:
- config-driven inference service that loads model and pipeline configs
- replaceable stub adapter bundle for vehicle, plate, OCR, and attribute stages
- frame-to-candidate workflow helper for the local capture-to-inference path
- inference profiling helpers for latency benchmarking and deployment recommendations
