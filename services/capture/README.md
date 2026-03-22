# Capture Service

Own camera discovery, frame acquisition, reconnect behavior, and camera metadata normalization.

Design rule:
- preserve image quality and timing fidelity before any downstream AI step

Current integrated slice:
- camera registry loader for validated camera configs
- registry discovery from a directory of camera configs for deployed-rig validation
- file-backed frame source for local testing and deterministic ingestion
- frame envelope generation with camera profile and GPS metadata attachment
- in-process queue handoff into the headless ingest runner so capture can feed downstream stages without hardware
- RTSP and USB live-source adapters with reconnect handling and local evidence writes
- optional live GPS provider hook for runtime capture sources
