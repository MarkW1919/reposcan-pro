# IMPLEMENTATION_BLUEPRINT.md

This document bridges the current design set and the first real implementation pass. It defines the intended service topology, contract boundaries, configuration ownership, and repo layout without introducing implementation code.

## Purpose

Use this blueprint when turning the fresh scaffold into working services. If a proposed implementation conflicts with this document, `CLAUDE.md`, or the canonical docs, pause and resolve the architecture question before writing code.

## System Topology

```text
Camera Source
  -> Capture Service
  -> Preprocessing Service
  -> Inference Service
  -> Tracking Service
  -> Storage Service
  -> Alerting Service
  -> API App
  -> UI App
                 \
                  -> Sync Service (optional, asynchronous)
```

## Runtime Design Rules

- keep the camera-to-storage path local and operational without internet
- keep the sync path asynchronous and outside the critical inference path
- let configuration choose models, pipelines, and deployment profiles
- preserve raw evidence and intermediate confidence where operator review matters
- optimize for usable reads in bad conditions, not only average-case benchmarks

## Service Responsibilities

### `services/capture`

Own:
- camera discovery and registration
- frame acquisition from RTSP, USB, or file-backed test sources
- timestamping, camera metadata attachment, and reconnect behavior
- publishing a normalized frame envelope for downstream processing

Do not own:
- model inference
- OCR decisions
- persistent business records

### `services/preprocessing`

Own:
- scene-aware enhancement decisions
- plate-safe normalization, denoising, and contrast handling
- crop rectification helpers for OCR-ready regions

Do not own:
- final OCR decoding
- long-term storage
- direct UI concerns

### `services/inference`

Own:
- vehicle detection
- plate detection
- OCR invocation
- vehicle color and make/model classification
- config-driven model loading and model metadata reporting

Do not own:
- tracker identity lifecycle
- authoritative persistence
- hotlist policy

### `services/tracking`

Own:
- vehicle association across frames
- OCR candidate aggregation across a track
- best-read promotion logic
- duplicate suppression rules

Do not own:
- model execution
- media retention policy

### `services/storage`

Own:
- local-first metadata persistence
- media path registration
- review state persistence
- retrieval primitives needed by API and sync

Do not own:
- live inference
- external sync orchestration

### `services/alerting`

Own:
- exact and normalized hotlist matching
- alert event generation
- durable local alert history

Do not own:
- upstream sync delivery
- OCR correction workflows

### `services/sync`

Own:
- queueing outbound records for remote sync
- retry and backoff behavior
- remote delivery status updates

Do not own:
- authoritative local persistence
- blocking the local detection pipeline

### `apps/api`

Own:
- health, detection, alert, hotlist, and review endpoints
- contract validation at the application boundary
- auth and audit plumbing when introduced

Do not own:
- direct model execution
- camera capture loops

### `apps/ui`

Own:
- operator workflows for live monitoring, review, search, and alert handling
- read and mutation flows through the API only

Do not own:
- direct access to databases or model runtimes

## Planned Inter-Service Contracts

### `FrameEnvelope`

Produced by capture, consumed by preprocessing.

Required fields:
- `frame_id`
- `camera_id`
- `timestamp_utc`
- `frame_path` or in-memory frame handle
- `camera_profile`
- `gps_snapshot` when available
- `source_type`

### `InferenceCandidate`

Produced by inference, consumed by tracking and storage.

Required fields:
- `frame_id`
- `camera_id`
- `vehicle_detections`
- `plate_detections`
- `ocr_candidates`
- `attribute_predictions`
- `model_versions`
- `processing_latency_ms`

### `TrackedDetection`

Produced by tracking, consumed by storage and alerting.

Required fields:
- `detection_id`
- `tracker_id`
- `best_plate_candidate`
- `alternate_plate_candidates`
- `vehicle_attributes`
- `evidence_refs`
- `confidence_summary`
- `timestamp_utc`

### `StoredDetection`

Produced by storage, consumed by API and sync.

Required fields:
- all fields from the canonical detection record in [API_CONTRACTS.md](API_CONTRACTS.md)
- storage-specific media references
- review status
- alert linkage when applicable

## Configuration Ownership

The first real code pass should standardize configuration under `configs/`:

```text
configs/
├─ cameras/
│  └─ example-camera.yaml
├─ models/
│  └─ example-model-stack.yaml
├─ pipelines/
│  └─ default-edge.yaml
└─ deployments/
   └─ local-dev.yaml
```

### Cameras

Store:
- camera identifiers
- stream URLs or device bindings
- sensor and optics notes
- exposure and frame-rate preferences
- mounting and orientation metadata

### Models

Store:
- detector, OCR, classifier, and tracker model selections
- artifact paths
- expected input sizes and normalization settings
- export/runtime compatibility metadata

### Pipelines

Store:
- full-frame versus vehicle-crop plate detection strategy
- preprocessing toggles
- confidence thresholds
- tracking and fusion settings

### Deployments

Store:
- local workstation defaults
- Jetson or edge deployment profiles
- enabled services and local infrastructure dependencies

## Storage Layout Direction

Use Postgres/PostGIS for structured metadata and local filesystem storage for media.

Planned local media roots:

```text
media/
├─ frames/
├─ crops/
├─ snippets/
└─ exports/
```

Design rules:
- metadata rows should reference media paths instead of embedding large payloads
- media retention policy must be configurable
- storage failures must surface clearly and fail safely

## Initial Code Layout Direction

The next scaffold pass should introduce these source roots:

```text
apps/api/src/
apps/ui/src/
packages/contracts/src/
services/capture/src/
services/preprocessing/src/
services/inference/src/
services/tracking/src/
services/storage/src/
services/alerting/src/
services/sync/src/
ml/training/experiments/
ml/inference/adapters/
tests/contracts/
tests/integration/
tests/manual/
```

Ownership expectations:
- keep shared schemas in `packages/contracts`
- keep service-local logic inside the owning service
- keep model-training concerns out of runtime services
- keep API and UI dependent on contracts, not on direct service internals

## Phase Order For Implementation

### Phase 1: Contracts And Config Foundations

- define shared schemas for detections, alerts, reviews, hotlists, and health
- define config file formats for cameras, models, and deployment profiles
- wire validation and loading rules before service behavior grows

### Phase 2: Local Storage And API Skeleton

- stand up metadata persistence and media path conventions
- add health endpoints and read-only detection retrieval paths
- establish audit-ready review update primitives

### Phase 3: Capture And Inference Skeleton

- add camera ingestion and test-source ingestion
- add inference orchestration stubs around config-driven model adapters
- define end-to-end frame-to-candidate flow without optimizing prematurely

### Phase 4: Tracking, Alerting, And Review Loop

- add tracker identity and OCR fusion
- add hotlist matching and alert persistence
- complete operator review and correction flows

### Phase 5: Edge Optimization And Sync

- benchmark ONNX and TensorRT export paths
- tune latency and memory use on target hardware
- add optional remote sync without disturbing local-first guarantees

## Ready-For-Code Gate

Before implementation starts, the following should be true:
- the service ownership model above is accepted
- the shared contracts are accepted at a schema level
- the configuration layout under `configs/` is accepted
- the first implementation phase is limited to contracts, config loading, storage, and API foundations

## Related Documents

- [CLAUDE.md](../CLAUDE.md)
- [Architecture](ARCHITECTURE.md)
- [API Contracts](API_CONTRACTS.md)
- [Deployment](DEPLOYMENT.md)
- [Requirements](REQUIREMENTS.md)
