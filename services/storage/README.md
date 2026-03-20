# Storage Service

Own local-first persistence for metadata, crops, media references, and review state.

Design rule:
- loss of internet connectivity must not block recording detections

Current Phase 4 skeleton:
- media layout helper for `media/frames`, `media/crops`, `media/snippets`, and `media/exports`
- repository boundary for detections and reviews
- in-memory repository for tests
- JSON-backed repository for local metadata persistence during the skeleton phase
- storage service wrapper used by the API health, detection, and review flows
- alert and hotlist persistence primitives for the Phase 4 operator loop
