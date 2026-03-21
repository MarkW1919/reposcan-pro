# OPERATIONS_AND_LOGGING.md

This document defines the baseline logging and operational expectations for RepoScan Pro from capture through UI.

The goal is not verbose logging for its own sake. The goal is to make failures, state transitions, and field-relevant behavior visible without drowning operators or developers in noise.

## Logging Principles

- keep logs structured and machine-readable where possible
- log lifecycle boundaries, state changes, failures, retries, and validation-relevant metrics
- prefer correlation identifiers over ambiguous prose
- never require internet connectivity for core operational visibility
- do not log secrets, auth tokens, or raw binary payloads
- do not emit full image payloads or large blobs into logs

## Common Log Fields

Every subsystem should log a consistent subset of the following fields when they apply:

- `timestamp_utc`
- `level`
- `service`
- `event`
- `message`
- `run_id`
- `sequence_id`
- `camera_id`
- `frame_id`
- `detection_id`
- `tracker_id`
- `alert_id`
- `hotlist_entry_id`
- `review_id`
- `operator_id`
- `status`
- `latency_ms`
- `error_type`
- `retry_count`

## Log Levels

- `DEBUG`: development-only diagnostics, model-selection details, intermediate timings, and local troubleshooting output
- `INFO`: startup, shutdown, successful state transitions, accepted operator actions, and periodic health summaries
- `WARN`: degraded but non-fatal behavior such as reconnects, retries, fallback paths, missing optional media, or suppressed sync
- `ERROR`: failed operations that prevented expected work from completing

## Operational Notes By Subsystem

## Capture

Required log events:
- service startup and camera/profile selection
- source registration and source type (`file`, `rtsp`, `usb`)
- frame acquisition start and stop
- reconnect attempts and reconnect success
- queue backpressure or dropped-frame warnings
- capture failure with camera/source context

Operational notes:
- preserve timing fidelity and camera metadata before downstream processing
- surface reconnect and source-read failures quickly
- treat frame loss as operationally important even when the process survives

## Preprocessing

Required log events:
- preprocessing enabled or disabled for a run
- chosen enhancement path for a frame batch or sequence
- passthrough fallback when a frame is missing or undecodable
- artifact output path when debug artifacts are written
- preprocessing latency summaries

Operational notes:
- enhancement should never silently replace raw evidence
- fallback behavior must be visible so low-quality runs are not mistaken for successful enhancement

## Inference

Required log events:
- model stack selection from configuration
- runtime adapter selection
- per-stage latency summaries for vehicle, plate, OCR, and attributes
- inference failure with stage ownership
- benchmark/profiling recommendations when profiling is active

Operational notes:
- log model identity and runtime path for every promoted configuration
- keep stage ownership clear so detector failures are distinguishable from OCR failures

## Tracking

Required log events:
- track creation and finalization
- best-read promotion events
- duplicate suppression decisions when applicable
- track aggregation summaries for finalized detections

Operational notes:
- logs should make it possible to understand why a plate candidate was promoted
- fusion behavior should remain explainable during review and regression checks

## Storage

Required log events:
- metadata store initialization
- media layout initialization
- detection, alert, review, and hotlist persistence success/failure
- low-storage or retention-related warnings once implemented
- recovery behavior after store or write failures

Operational notes:
- storage failures are mission-critical and must surface clearly
- logs should distinguish metadata persistence failures from missing media files

## Alerting

Required log events:
- hotlist match decisions with match type and confidence
- alert creation
- alert status transitions (`active`, `acknowledged`, `dismissed`)
- suppressed-popup behavior for dismissed alerts

Operational notes:
- alert lifecycle transitions should be audit-friendly
- stand-down behavior must be visible so popup suppression is explainable later

## Sync

Required log events:
- enqueue, dequeue, retry, and terminal sync outcomes
- remote transport selection
- retry backoff timing
- `sync_status` transitions on affected records

Operational notes:
- sync must remain outside the mission-critical path
- remote failures should be noisy in logs but must not imply local data loss

## API

Required log events:
- service startup and dependency health summary
- request handling failures with route and error type
- operator mutation events for reviews, hotlists, alerts, and demo runtime control
- media-endpoint misses for frame and crop retrieval

Operational notes:
- the API is the audit boundary for operator-visible mutations
- logs should make it possible to trace a user action to the affected record identifiers

## UI

Required log events:
- client-side error reporting hooks once centralized reporting is added
- live API connection state transitions
- demo fallback activation
- operator-action submission failures surfaced to the interface

Operational notes:
- the UI should prefer operator-facing status messaging over silent failure
- local fallback mode should be obvious so demo behavior is not mistaken for live persistence

## Health And Visibility Expectations

Every subsystem should eventually expose or feed into:

- startup visibility
- current health/degraded state
- the last failure reason when degraded
- enough identifiers to trace an end-to-end event from source frame to stored alert

## Minimum End-To-End Traceability

For a single hotlist hit, operators and developers should be able to trace:

1. the source camera and frame
2. preprocessing behavior
3. inference candidate creation
4. track promotion into a stored detection
5. alert generation and lifecycle changes
6. API retrieval and UI presentation
7. optional sync attempts if enabled later

## Implementation Guidance

- prefer structured logging helpers over ad hoc string formatting once runtime logging is widened
- keep high-volume debug logs behind configuration switches
- include logging impact notes in future PRs or milestone summaries
- update this document when a new subsystem or operator-critical workflow is introduced

## Related Documents

- [Requirements](REQUIREMENTS.md)
- [Architecture](ARCHITECTURE.md)
- [Deployment](DEPLOYMENT.md)
- [UI Workflows](UI_WORKFLOWS.md)
