# OPERATOR_TRAINING.md

Training material for RepoScan Pro field operators. This document covers the first-shift workflows needed to run the local-first vehicle recognition system safely on a truck-mounted workstation.

## Training Goals

After training, an operator must be able to:

- start the local edge runtime and verify camera, inference, storage, and sync status
- monitor live detections without interrupting the driver workflow
- respond to hotlist alerts using acknowledge, stand down, reopen, review, and follow-up actions
- search detections by plate, camera, vehicle attributes, alert state, and address-oriented context
- export evidence for handoff without depending on internet connectivity
- operate through an internet outage and confirm queued sync recovers later
- stop capture when required by policy, property-owner instruction, law-enforcement instruction, or unsafe conditions

## Session 1: Workstation And Runtime Startup

1. Launch the RepoScan Pro operator workstation.
2. Open the operator UI.
3. Confirm the System panel shows the expected data source, API state, edge runtime state, online camera count, and storage health.
4. Start or restart the edge runtime only when the vehicle is parked or the driver confirms it is safe.
5. Confirm live detections begin updating before leaving the setup area.

Pass condition: the operator can identify whether the system is in demo, fallback, live, degraded, or offline state without assistance.

## Session 2: Live Monitoring

1. Keep the console screen visible during route scanning.
2. Use camera and map views to confirm whether detections are coming from the expected camera positions.
3. Treat confidence, alternate plate candidates, vehicle attributes, GPS, and timestamp as a combined signal.
4. Avoid acting on a low-confidence plate read until the detail view, image evidence, or repeated observations support it.

Pass condition: the operator can open a detection, inspect frame and crop evidence, and explain the confidence summary.

## Session 3: Alerts And Recovery Accounts

1. When a hotlist alert appears, open the alert case before taking action.
2. Compare plate text, alternate OCR candidates, vehicle color, make/model, timestamp, camera, and GPS.
3. Use `Acknowledge` for an active response, `Stand down` for a ruled-out match, and `Reopen` if later evidence changes the decision.
4. Add response notes that state the reason for the decision.
5. Use follow-ups for cases that need later operator review or dispatch.

Pass condition: the operator can resolve a true positive and a false positive with persistent notes.

## Session 4: Search And Review

1. Search by full or partial plate when validating a recovery account.
2. Use camera, vehicle, alert-state, and date filters to narrow large result sets.
3. Use review actions to confirm correct reads, correct a plate, flag uncertain evidence, or dismiss unusable detections.
4. Confirm review history appears in detection details and remains available after refresh.

Pass condition: the operator can find a prior detection, correct a plate read, and verify the correction is persisted.

## Session 5: Route And Address Workflow

1. Select a destination from recent, account-linked, or manually entered addresses.
2. Confirm arrival radius and active scan state before relying on address-scoped popup behavior.
3. Keep hotlist alerting enabled unless instructed otherwise; hotlist alerts are higher priority than address-scoped local popups.
4. If the address scan is disabled, verify the UI clearly shows that local address popups are suppressed.

Pass condition: the operator can explain the difference between hotlist alerts and address-scoped popup activity.

## Session 6: Local-First Outage Operation

1. If internet is unavailable, continue local capture unless safety or policy requires stopping.
2. Confirm detections and alerts still persist locally.
3. Confirm sync status shows queued or local-only state while offline.
4. After reconnect, confirm the queue drains and records move to synced state.

Pass condition: the operator can continue work during an outage and verify recovery without losing local evidence.

## Session 7: Evidence Export

1. Open the selected detection.
2. Verify frame, plate crop, timestamp, GPS, camera ID, OCR candidates, and review state.
3. Export the detection package.
4. Open the exported package on the workstation before handoff.

Pass condition: the operator can produce a self-contained evidence package that does not require the running UI.

## Session 8: Stop Conditions

Stop or pause capture when:

- a law-enforcement officer instructs the team to stop
- a property owner or authorized site representative instructs the team to leave
- the camera placement creates a driving or pedestrian hazard
- weather, vibration, glare, or obstruction makes evidence unreliable
- the workstation reports low storage below the deployment threshold
- the driver needs the operator's attention for vehicle safety

Pass condition: the operator can name the stop conditions and find the runtime stop control.

## Pilot Scoring

Use [OPERATOR_UX_PILOT.md](OPERATOR_UX_PILOT.md) and [operator_pilot_scoring_template.csv](operator_pilot_scoring_template.csv) to score the pilot. A production-readiness review should not accept operator readiness until all pilot tasks have scored outcomes and no show-stopper findings remain open.

## Handoff Checklist

- operator completed all eight sessions
- operator demonstrated live monitoring, alert response, search, review, outage behavior, and evidence export
- supervisor reviewed response-note quality
- workstation profile, API token handling, and stop conditions were explained
- pilot score sheet or training signoff was stored with the deployment record

