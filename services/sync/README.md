# Sync Service

Handle optional upstream synchronization without becoming part of the mission-critical path.

Design rule:
- queue locally, retry safely, and degrade gracefully when remote systems are unavailable

Current capabilities:
- JSON-backed local queue for detection sync jobs
- pluggable transport boundary for remote delivery
- HTTP sync transport with idempotency-key support
- exponential backoff retries with local `sync_status` updates
- idempotent conflict handling for replayed detections
- reproducible remote-endpoint evidence via a local HTTP fixture server

Refresh the repo-tracked Section 7 sync evidence report with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_sync_remote_evidence.py --output-root .\services\sync\fixtures --overwrite
```
