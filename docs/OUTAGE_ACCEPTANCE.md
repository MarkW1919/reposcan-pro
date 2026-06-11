# OUTAGE_ACCEPTANCE.md

The internet-outage acceptance harness produces the evidence artifacts that close §12.182 of [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) and feed rows P6-1, P6-2, and NF-3 in the evidence register of [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

The harness drives a realistic capture -> storage -> alerting -> sync flow inside the repo process with every outbound transport forced offline. It verifies the local-first invariants hold during the outage, restores the transports, and checks that the queued state drains cleanly on recovery.

## What it proves

- local detection storage never blocks on upstream sync reachability
- hotlist alerts are persisted locally even when the webhook is unreachable
- the sync queue retains unsynced items with correct retry state
- detection rows show `sync_status=failed` and `local_only_flag=True` during the outage
- the outage path is exercised, not silently bypassed (retry counters are non-zero)
- when upstream returns, the queue drains in a single scheduled sync pass
- detection rows flip back to `sync_status=synced` and `local_only_flag=False`
- previously undelivered alerts can be re-delivered successfully

These invariants are checked every run and listed individually in the output report, so a reviewer can see exactly which guarantee passed or failed.

## When to use it

Run the outage harness every time any of these change:

- the sync service, queue schema, or retry policy changes
- the alert delivery path or transport changes
- the storage repository backend changes
- a production-readiness review is about to be signed

Unlike the hardware-gated acceptance lanes, this harness does not require field captures or the target-device rig. It is a pure software acceptance run and can be executed on any workstation or in CI.

## Prerequisites

- a deployment config (defaults to `configs/deployments/local-dev.yaml`) that selects the storage backend for the run
- a pipeline config (defaults to `configs/pipelines/default-edge.yaml`) used by the alerting service for threshold evaluation

The harness materializes its own isolated workspace directory so repeated runs never pollute developer state.

## Invocation

On Windows:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_outage_acceptance.py `
  --deployment-config .\configs\deployments\local-dev.yaml `
  --detection-count 10
```

Key flags:

- `--deployment-config` (default `configs/deployments/local-dev.yaml`)
- `--pipeline-config` (default `configs/pipelines/default-edge.yaml`)
- `--detection-count` (default 10): number of synthetic detections driven through the flow
- `--hotlist-plate` (default `HOTLIST1`): plate text used for the hotlist entry; the first detection matches it so the alerting path is exercised
- `--output-root` (default `artifacts/acceptance/outage`)
- `--workspace-root` (optional): explicit workspace directory; defaults to `<output-root>/<run-id>/workspace`
- `--run-id` (default: auto-generated `outage_<utc-timestamp>`)

Exit code is `0` when every invariant passed and `1` when any invariant failed. CI pipelines can consume this directly.

## Output layout

Every run lands in `artifacts/acceptance/outage/<run_id>/`:

```text
artifacts/acceptance/outage/<run_id>/
|-- run_manifest.json   # run id, deployment, pass/fail, per-invariant summary
|-- production_readiness_evidence.json # P6/NF criterion-to-artifact evidence map
|-- outage_report.json  # full OutageAcceptanceReport sidecar
`-- outage_report.md    # operator-readable summary with phase snapshot + invariant tables
```

The workspace directory under `<run_id>/workspace/` holds the run's isolated storage metadata and sync queue. It is safe to delete after the run.
The `production_readiness_evidence.json` sidecar binds the outage run to P6-1, P6-2, and NF-3 so reviewers can trace local-first evidence without hand-mapping invariant names to readiness rows.

## How the outage is simulated

Two transports are installed before any data flows through the pipeline:

- `OfflineSyncTransport` (in `reposcan_sync`) raises `RetryableSyncTransportError` on every call, matching the behavior of the real `HttpSyncTransport` when the network is unreachable
- `OfflineAlertDeliveryTransport` (in `reposcan_sync.outage_runner`) raises `RetryableAlertDeliveryError` on every call, matching the real `WebhookAlertDeliveryTransport`

The harness drives detections and one hotlist-matching alert through the pipeline with these transports in place, then snapshots storage, the sync queue, and the delivery counters.

## How the recovery is simulated

After the outage snapshot, the harness swaps in `MemorySyncTransport` and `MemoryAlertDeliveryTransport` (both of which accept every call) and calls `SyncService.run_once` with a `now_utc` value far enough in the future that every retry-gated queue item is ready. It then re-delivers every persisted alert.

The recovery snapshot is then compared against the expected steady-state and each invariant is scored.

## Invariants checked

| phase | name | what it asserts |
|---|---|---|
| outage | local_detections_persist_during_outage | every ingested detection landed in local storage |
| outage | local_alerts_persist_during_outage | the hotlist match produced an alert row in local storage |
| outage | sync_queue_retains_pending_items | the sync queue has an entry per unsynced detection |
| outage | detections_marked_local_only_during_outage | every detection shows `sync_status=failed` + `local_only_flag=True` |
| outage | offline_transports_were_actually_exercised | the offline sync + alert transports were invoked at least once |
| recovery | sync_queue_drains_on_recovery | sync queue depth returns to 0 |
| recovery | detections_flip_to_synced_on_recovery | every detection shows `sync_status=synced` |
| recovery | alerts_redeliver_on_recovery | the persisted alert was delivered on recovery |

Any failing invariant fails the whole run. Add new invariants by extending `_evaluate_invariants` in [services/sync/src/reposcan_sync/outage_runner.py](../services/sync/src/reposcan_sync/outage_runner.py).

## Contract with the rest of the repo

- the harness does not reimplement the sync, alerting, or storage services; it imports the production types directly
- the harness owns an isolated workspace and never touches `runtime/storage` or `runtime/sync`
- the harness does not edit `PRODUCTION_READINESS.md`; the reviewer reads the generated `outage_report.md` and updates the evidence register
- changing the sync retry policy or adding a new invariant requires updating both the runner and this document

## Related Documents

- [Acceptance Harness](ACCEPTANCE_HARNESS.md)
- [Edge Bench](EDGE_BENCH.md)
- [Production Readiness](PRODUCTION_READINESS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
