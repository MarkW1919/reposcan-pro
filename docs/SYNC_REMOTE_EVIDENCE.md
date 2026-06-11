# SYNC_REMOTE_EVIDENCE.md

This document records the repo-tracked evidence that closes the remaining Section 7 alerting-and-sync checklist items.

These artifacts prove HTTP remote sync delivery, retry/replay behavior against a real local endpoint, idempotent conflict handling, and optional alert webhook fan-out.
They do not claim internet-outage field acceptance or final upstream production infrastructure signoff.

## Repo-Tracked Evidence

- remote sync and alert delivery report:
  - [services/sync/fixtures/reports/remote-sync-validation.json](../services/sync/fixtures/reports/remote-sync-validation.json)

## Current Baseline

From the repo-tracked evidence report:

- first remote sync run fails once with a retryable upstream response: `first_run_failed = 1`
- queued replay succeeds on retry: `retry_run_synced = 1`
- replaying the same detection again is treated as idempotent success: `idempotent_replay_synced = 1`
- the remote endpoint receives only `1` unique detection even though it sees `3` sync posts
- final detection `sync_status` ends as `synced`
- alert webhook delivery reaches the endpoint with `1` unique alert across `2` posts, proving duplicate alert delivery is also idempotent-safe

## Regenerate

Refresh the evidence report with:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_sync_remote_evidence.py --output-root .\services\sync\fixtures --overwrite
```

## Scope Boundary

This evidence is enough to close Section 7 remote transport, replay validation, conflict/idempotency handling, and optional alert delivery integration.

It is not enough to close:

- Section 12 internet-outage acceptance validation
- Section 13 full-system field-readiness gates
