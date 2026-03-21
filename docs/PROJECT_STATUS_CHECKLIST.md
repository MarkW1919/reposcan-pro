# Project Status Checklist

Reference only. This file is the master build checklist for RepoScan Pro from foundation through field-ready deployment.

Status convention:
- completed items use `- [x] ~~item~~`
- incomplete items use `- [ ] item`

Last reviewed against repo state: `2026-03-21`

## 1. Program Foundations

- [x] ~~Canonical design and execution docs are present and accepted (`CLAUDE.md`, architecture, requirements, blueprint, deployment, API, UI workflows).~~
- [x] ~~Repository layout exists for apps, services, packages, configs, scripts, and tests.~~
- [x] ~~Shared contracts package exists and is importable across services.~~
- [x] ~~Typed config schemas exist for camera, model, pipeline, and deployment profiles.~~
- [x] ~~Config loaders and validation tests exist for the supported config types.~~
- [x] ~~Example and local development configs exist for camera, model stack, pipeline, and deployment.~~
- [x] ~~Bootstrap, check, desktop launcher, and headless demo helper scripts exist.~~
- [x] ~~Architecture-decision tracking is actively maintained as implementation evolves.~~
- [x] ~~Subsystem logging standards and operational notes are documented end to end.~~

## 2. Camera And Imaging

- [x] ~~Normalized frame-envelope contract exists for downstream processing.~~
- [x] ~~Camera registry loading exists for validated camera configs.~~
- [x] ~~File-backed capture source exists for deterministic local testing.~~
- [x] ~~Capture can hand frames into the headless ingest runtime without hardware.~~
- [ ] RTSP ingest path is implemented.
- [ ] USB ingest path is implemented.
- [ ] Live camera reconnect behavior is implemented and validated.
- [ ] Live GPS ingestion is wired from deployment hardware.
- [ ] Camera discovery and registration workflow is implemented for deployed rigs.
- [ ] Camera placement, vibration, and angle-of-incidence validation workflow is documented and repeatable.
- [ ] Required long-distance imaging validation scenes are captured and reviewed.
- [ ] Required low-light, no-light, glare, and IR-assisted validation scenes are captured and reviewed.

## 3. Preprocessing

- [x] ~~Prepared-frame contract exists and preserves raw evidence references.~~
- [x] ~~Preprocessing can write local debug artifacts during headless ingest.~~
- [x] ~~Basic denoising and low-light-oriented contrast enhancement are implemented.~~
- [x] ~~Safe passthrough behavior exists when frames are missing or undecodable.~~
- [ ] Exposure-aware scene tuning is implemented.
- [ ] OCR crop rectification helpers are implemented.
- [ ] Production-grade CLAHE / OpenCV-oriented enhancement path is implemented.
- [ ] Preprocessing impact on OCR and low-light performance is benchmarked and documented.

## 4. Inference Runtime

- [x] ~~Config-driven inference orchestration boundary exists.~~
- [x] ~~Replaceable adapter bundle exists for vehicle, plate, OCR, and attribute stages.~~
- [x] ~~Headless frame-to-candidate workflow is integrated into the local runtime path.~~
- [x] ~~Latency profiling helper exists for inference benchmarking.~~
- [ ] Real vehicle detector runtime is integrated.
- [ ] Real plate detector runtime is integrated.
- [ ] Real OCR runtime is integrated.
- [ ] Real color classifier runtime is integrated.
- [ ] Real make/model classifier runtime is integrated.
- [ ] Optional vehicle-year prediction runtime is integrated.
- [ ] Promoted runtime models export cleanly to ONNX.
- [ ] Target edge runtime models validate cleanly under TensorRT or equivalent.
- [ ] Long-range inference accuracy benchmarks exist for promoted runtime models.
- [ ] Low-light inference accuracy benchmarks exist for promoted runtime models.

## 5. Tracking And Fusion

- [x] ~~Tracked-detection contract exists for downstream storage and alerting.~~
- [x] ~~Stateful multi-frame association exists in the tracking service.~~
- [x] ~~OCR candidate fusion and best-read promotion exist.~~
- [x] ~~Tracked detections flow into storage and alerting in the headless runtime.~~
- [ ] Tracker identity lifecycle is hardened for crowded scenes and camera motion.
- [ ] Duplicate suppression is benchmarked and tuned for repeated passes.
- [ ] Alternate tracker strategies are evaluated against field-relevant workloads.

## 6. Storage And Media

- [x] ~~Local media layout exists for frames, crops, snippets, and exports.~~
- [x] ~~Detection persistence exists behind a storage-service boundary.~~
- [x] ~~Review persistence exists.~~
- [x] ~~Alert persistence exists.~~
- [x] ~~Hotlist persistence exists.~~
- [x] ~~JSON-backed local metadata persistence exists.~~
- [x] ~~In-memory repository exists for tests and local wiring.~~
- [x] ~~Development seed data exists for operator demo flows.~~
- [ ] Postgres/PostGIS metadata backend is implemented.
- [ ] Media retention enforcement jobs are implemented.
- [ ] Disk-pressure handling and low-storage response paths are implemented.
- [ ] Evidence export packaging is implemented for operator handoff.
- [ ] Storage recovery behavior is hardened for real crash and restart scenarios.

## 7. Alerting And Sync

- [x] ~~Exact and normalized hotlist matching exist.~~
- [x] ~~Alert thresholding exists through the pipeline configuration path.~~
- [x] ~~Durable local alert history exists.~~
- [x] ~~Local sync queue skeleton exists with retry/backoff behavior and `sync_status` updates.~~
- [ ] Production remote transport is implemented.
- [ ] Remote sync replay is validated against a real endpoint.
- [ ] Sync conflict handling and idempotency behavior are defined and tested.
- [ ] Optional alert delivery integrations beyond the local UI are implemented where required.

## 8. API Application

- [x] ~~FastAPI app factory and ASGI entrypoint exist.~~
- [x] ~~Health endpoint exists.~~
- [x] ~~Dashboard overview endpoint exists.~~
- [x] ~~Detection list and detail endpoints exist.~~
- [x] ~~Detection evidence frame endpoint exists.~~
- [x] ~~Detection plate-crop endpoint exists.~~
- [x] ~~Review create and list endpoints exist.~~
- [x] ~~Alert list, detail, and update endpoints exist.~~
- [x] ~~Hotlist list, create, and update endpoints exist.~~
- [x] ~~Demo runtime start and status endpoints exist.~~
- [ ] Search endpoints exist for plate, date, camera, GPS region, vehicle attributes, and alert state.
- [ ] Authentication and authorization are implemented.
- [ ] Audit logging surfaces are implemented.
- [ ] API rate limiting and production hardening are implemented.
- [ ] API versioning and external integration guidance are finalized.

## 9. UI Application And Operator Workflows

- [x] ~~Operator UI shell exists for dashboard, route HUD, recovery alerts, camera views, and field settings.~~
- [x] ~~Layout presets and browser-persisted custom layout behavior exist.~~
- [x] ~~Live dashboard overview integration exists with demo fallback when the API is offline.~~
- [x] ~~Popup activity stream exists with hotlist and address-scan behavior rules.~~
- [x] ~~Selected-alert evidence preview exists for live frame and plate-crop media when available.~~
- [x] ~~Hotlist management workflow exists in the UI.~~
- [x] ~~Review workflow exists with confirm, correct, flag, dismiss, and persisted review history.~~
- [x] ~~Alert response workflow exists with acknowledge, stand down, reopen, and persisted response notes.~~
- [x] ~~App-driven headless demo runtime controls exist in the UI.~~
- [x] ~~Recovery log can reflect live alert status changes.~~
- [ ] Search workflow UI exists for full and partial plate search.
- [ ] Rich detection detail view exists for alternate OCR candidates and confidence breakdowns.
- [ ] Pin / follow-up workflow exists for high-value detections.
- [ ] Dispatch / assignment workflow exists beyond the current alert lifecycle controls.
- [ ] Multi-user session awareness exists.
- [ ] Role-based permissions exist.

## 10. Datasets And Training

- [ ] Local dataset layout exists for raw, staged, curated, eval, and manifest data.
- [ ] Dataset intake gate exists for provenance, license, and annotation review.
- [ ] Annotation standards exist for vehicles, plates, OCR text, attributes, and lighting metadata.
- [ ] Train/validation/holdout split strategy is implemented by capture session where possible.
- [ ] Dedicated field-eval holdouts exist for night and long-range regression checks.
- [ ] Vehicle detector fine-tuning workflow exists.
- [ ] Plate detector fine-tuning workflow exists for small, low-light targets.
- [ ] OCR fine-tuning workflow exists.
- [ ] Color classifier training workflow exists.
- [ ] Make/model classifier training workflow exists.
- [ ] Realistic augmentation suite exists and is documented.
- [ ] Field-relevant evaluation reports exist for exact match, character accuracy, low light, long range, latency, and export viability.
- [ ] Model promotion and rollback process exists with versioned artifacts kept outside git.

## 11. Deployment And Operations

- [x] ~~Local workstation deployment profile exists.~~
- [x] ~~Jetson Orin deployment profile scaffold exists.~~
- [x] ~~Local development workflow is scriptable from bootstrap through validation.~~
- [ ] Deterministic multi-service startup exists for target edge hardware.
- [ ] Watchdog-friendly process supervision exists for deployed services.
- [ ] Safe restart behavior after power loss or process failure is validated.
- [ ] Camera reconnect resilience is validated under deployment supervision.
- [ ] ONNX/TensorRT packaging is finalized for the target edge platform.
- [ ] Remote update, rollback, and artifact promotion plan is finalized.
- [ ] Structured logging, metrics, and runtime visibility are implemented across services.
- [ ] Secrets handling and security hardening are implemented for deployment.
- [ ] Field installer or packaged deployment workflow exists for laptop and edge-device setup.

## 12. Validation, Demo, And Acceptance

- [x] ~~Contract tests exist.~~
- [x] ~~Integration tests exist for API, storage, capture/inference flow, tracking/alerting flow, inference profiling, and sync skeleton behavior.~~
- [x] ~~Manual demo checklist exists.~~
- [x] ~~No-hardware headless demo flow exists from frame folder through UI-visible detections and alerts.~~
- [x] ~~The current integrated repo validates cleanly with `npm run check`, `pytest`, and `npm run ui:build`.~~
- [ ] Hardware-in-the-loop capture validation exists.
- [ ] Long-range plate-readability acceptance run exists.
- [ ] Low-light / no-light acceptance run exists.
- [ ] Moving-vehicle and moving-platform acceptance run exists.
- [ ] Internet-outage local-first acceptance run exists.
- [ ] Edge latency and memory benchmark report exists on target hardware.
- [ ] Operator UX pilot results are captured and incorporated.
- [ ] Production-readiness review and go/no-go checklist are completed.

## 13. Full-System Completion Gate

- [ ] The system can ingest from deployed cameras without internet dependency.
- [ ] The system can produce reliable long-range plate reads in field-realistic conditions.
- [ ] The system can maintain usable performance in low-light and no-light-assisted conditions.
- [ ] The system can persist detections, media references, alerts, reviews, and hotlists locally first.
- [ ] The system can serve operator workflows for live monitoring, evidence review, search, and alert handling.
- [ ] The system can optionally sync upstream without blocking local mission-critical operation.
- [ ] The system is validated on target hardware with acceptable latency, stability, and recovery behavior.
- [ ] The system has completed field validation sufficient to call it fully working and functional.
