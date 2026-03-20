# Sync Service

Handle optional upstream synchronization without becoming part of the mission-critical path.

Design rule:
- queue locally, retry safely, and degrade gracefully when remote systems are unavailable

Current Phase 5 skeleton:
- JSON-backed local queue for detection sync jobs
- pluggable transport boundary for remote delivery
- exponential backoff retries with local `sync_status` updates
