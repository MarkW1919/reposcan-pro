# Capture Service

Own camera discovery, frame acquisition, reconnect behavior, and camera metadata normalization.

Design rule:
- preserve image quality and timing fidelity before any downstream AI step

Current Phase 3 skeleton:
- camera registry loader for validated camera configs
- file-backed frame source for local testing and deterministic ingestion
- frame envelope generation with camera profile and GPS metadata attachment
