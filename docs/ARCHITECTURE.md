# ARCHITECTURE.md

This document is the canonical high-level architecture reference for the fresh build.

## High-Level Pipeline

```text
Camera
→ Vehicle Detection
→ Plate Detection
→ Plate Crop
→ OCR
→ Classification
→ Tracking
→ Storage
→ Alerting
```

## Module Boundaries

### Capture
Handles camera input, timestamp alignment, camera metadata, reconnect behavior, and frame acquisition fidelity.

### Preprocessing
Performs image enhancement, normalization, and plate-crop conditioning without hallucinating signal that is not present.

### Detection
Runs vehicle and plate detection with strong recall and config-driven model selection.

### OCR
Transforms candidate plate crops into plate text, per-character confidence, full-string confidence, and alternate candidates.

### Classification
Predicts vehicle attributes such as color, make, and model while remaining optional when image quality is insufficient.

### Tracking
Associates detections across frames so the system can aggregate evidence and reduce duplicate reads.

### Storage
Persists detections, crops, review state, and media references locally first.

### API
Provides the external data contract for health, detections, alerts, review actions, and search.

### UI
Hosts operator workflows for live monitoring, review, search, and hotlist response.

## Runtime Topology

- `services/capture` owns camera ingestion and camera metadata normalization
- `services/preprocessing` owns frame conditioning and crop enhancement
- `services/inference` owns detector, OCR, and classifier orchestration
- `services/tracking` owns temporal association and best-read promotion
- `services/storage` owns local-first persistence
- `services/alerting` owns hotlist evaluation and alert fan-out
- `services/sync` owns optional upstream sync and queue replay
- `apps/api` exposes query and control interfaces
- `apps/ui` hosts the operator-facing client

## Design Rules

- keep capture, inference, storage, API, and UI as clearly separated concerns
- load models from configuration, not hardcoded paths
- preserve replaceable model boundaries
- treat low-light and long-range performance as first-class architecture inputs
- keep cloud connectivity out of the primary inference path

## Related Documents

- [Implementation Blueprint](IMPLEMENTATION_BLUEPRINT.md)
- [Requirements](REQUIREMENTS.md)
- [Camera And Imaging](CAMERA_AND_IMAGING.md)
- [Inference](INFERENCE.md)
- [API Contracts](API_CONTRACTS.md)
