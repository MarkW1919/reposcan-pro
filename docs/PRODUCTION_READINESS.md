# PRODUCTION_READINESS.md

Go / no-go review artifact for RepoScan Pro. When every criterion below has accepted evidence, the project is cleared to ship. Until then, this is the living checklist the review board works from.

## Purpose

This document is the single place where RepoScan Pro's shippability is decided. It does not duplicate the build checklist in [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md); it is the review surface for the hardware-gated and field-gated items in §12 and §13 of that checklist. The review board signs the decision record at the bottom of this file.

## Scope

In scope:

- RepoScan Pro local workstation deployment profile ([configs/deployments/local-dev.yaml](../configs/deployments/local-dev.yaml))
- RepoScan Pro Jetson Orin edge deployment profile ([configs/deployments/jetson-orin-edge.yaml](../configs/deployments/jetson-orin-edge.yaml))
- All subsystems listed in [CLAUDE.md](../CLAUDE.md) Required Subsystems
- API surface at `/api/v1` and the operator UI apps under [apps/](../apps/)

Out of scope for the first shipping decision:

- multi-region plate styles beyond the US baseline (see ADR-003 in [DECISIONS.md](DECISIONS.md))
- cloud-resident inference of any kind
- multi-tenant operator workflows

## Readiness Criteria

Criteria are organized by the engineering priority order in [CLAUDE.md](../CLAUDE.md). Each criterion must be a falsifiable statement, tied to a concrete evidence artifact (path given even when the artifact does not yet exist), and carry a threshold where applicable. A criterion is only `accepted` when a reviewer has read the evidence and signed off in the register below.

### P1 Long-range plate readability

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| P1-1 | Promoted OCR bundle achieves exact-match rate on the qualified `long_range` subset at least as high as the current baseline. | exact-match >= 1.0 on the internal fixture subset ([INFERENCE_RUNTIME_EVIDENCE.md](INFERENCE_RUNTIME_EVIDENCE.md) `long_range` baseline); exact-match >= 0.80 on the field-captured `long_range` holdout | [ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json](../ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json), `artifacts/acceptance/<run_id>/long_range_report.md` |
| P1-2 | Field-captured long-range acceptance run covers at least two capture sessions and at least four qualifying shots per range bucket. | qualified per [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md) | `artifacts/acceptance/<run_id>/long_range_report.md`, `artifacts/data/reports/<dataset>-qualification.json` |
| P1-3 | Plate pixel density at the stated target distance meets or exceeds the minimum documented in [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md). | measured plate width >= operator-documented minimum usable pixels | `artifacts/acceptance/<run_id>/plate_pixel_census.json` |

### P2 Low-light / no-light performance

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| P2-1 | Promoted OCR bundle achieves exact-match rate on the qualified `low_light` subset at least as high as the current baseline. | exact-match >= 0.857 on internal fixture subset; exact-match >= 0.70 on field-captured `low_light` holdout | [ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json](../ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json), `artifacts/acceptance/<run_id>/low_light_report.md` |
| P2-2 | Field-captured low-light / no-light acceptance run includes scenes across dusk, night, no-ambient, headlight glare, and IR-assisted illumination. | each of the five lighting buckets has >= 2 qualifying shots from distinct capture sessions | `artifacts/acceptance/<run_id>/low_light_report.md` |
| P2-3 | Preprocessing night-mode decision path chooses the low-light branch on the same frames that the OCR benchmark uses in its low-light subset. | decision match >= 0.95 across low-light subset | [docs/PREPROCESSING_BENCHMARK.md](PREPROCESSING_BENCHMARK.md), `artifacts/acceptance/<run_id>/preprocess_decision_audit.json` |

### P3 Stable real-time edge inference

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| P3-1 | End-to-end frame latency on target hardware stays below the profile's real-time budget at p95. | p95 end-to-end <= real-time budget declared in [configs/deployments/jetson-orin-edge.yaml](../configs/deployments/jetson-orin-edge.yaml) | `artifacts/bench/edge/<run_id>/edge_bench_report.md` |
| P3-2 | Peak RSS memory during a sustained run stays below the target device's documented ceiling. | peak RSS <= device ceiling in the edge deployment profile | `artifacts/bench/edge/<run_id>/edge_bench_report.json` |
| P3-3 | Cold-start to first-frame-ready on the target device completes within the documented startup budget. | startup time <= profile budget | `artifacts/bench/edge/<run_id>/edge_bench_report.json` |
| P3-4 | Watchdog-supervised multi-service startup returns to steady-state within the documented budget after a forced process kill of each subsystem in turn. | each subsystem recovery <= profile budget; zero silent data loss | `artifacts/recovery/<run_id>/subsystem_kill_matrix.md` |
| P3-5 | Camera reconnect resilience validated on target hardware against the RTSP and USB ingest paths. | reconnect success after each of >= 5 disconnect events per ingest path; zero silent data loss | `artifacts/recovery/<run_id>/camera_reconnect_report.md` |
| P3-6 | TensorRT promoted bundle passes deployment-profile validation on the Orin rig and executes the qualified benchmark without error. | `validate_edge_runtime_bundle.py` passes on Orin; benchmark completes | `artifacts/bench/edge/<run_id>/tensorrt_validation.json` |

### P4 OCR accuracy

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| P4-1 | Overall exact-match rate on the qualified eval holdout is at least as high as the current baseline. | overall exact-match >= 0.9 on internal fixture; overall exact-match >= 0.85 on field holdout | [ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json](../ml/inference/fixtures/reports/promoted-onnx-runtime.benchmark.json), `artifacts/acceptance/<run_id>/overall_report.md` |
| P4-2 | Character-level accuracy on the qualified eval holdout is at least as high as the current baseline. | char accuracy >= 0.986 internal; >= 0.95 field | same as P4-1 |
| P4-3 | Alternate OCR candidate surface is populated in the detection detail view for low-confidence reads and matches persisted review history. | >= 95% of low-confidence detections in the field run carry at least one alternate candidate | `artifacts/acceptance/<run_id>/ocr_candidate_audit.json` |

### P5 Vehicle classification accuracy

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| P5-1 | Color classifier top-1 accuracy on the qualified holdout is at least as high as the current baseline. | top-1 >= baseline in [PROMOTED_MODEL_BENCHMARKS.md](PROMOTED_MODEL_BENCHMARKS.md) | `artifacts/acceptance/<run_id>/color_report.md` |
| P5-2 | Make/model classifier top-1 accuracy on the qualified holdout is at least as high as the current baseline. | top-1 >= baseline in [PROMOTED_MODEL_BENCHMARKS.md](PROMOTED_MODEL_BENCHMARKS.md) | `artifacts/acceptance/<run_id>/make_model_report.md` |
| P5-3 | Vehicle year prediction, where enabled, degrades gracefully when OCR confidence is weak and never blocks detection persistence. | zero detection persistence failures attributable to year-prediction errors over the acceptance run | `artifacts/acceptance/<run_id>/year_failure_audit.json` |

### P6 Local-first storage and alerting

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| P6-1 | Internet-outage acceptance run demonstrates full local capture, inference, tracking, alerting, and persistence for at least the documented outage window with zero detection loss. | outage window >= 30 minutes; zero detections dropped; sync queue drains without data loss on reconnect | `artifacts/acceptance/<run_id>/outage_report.md` |
| P6-2 | Hotlist match alerts fire and persist during the outage window and remain acknowledgeable after reconnect. | zero missed alerts attributable to the outage window | `artifacts/acceptance/<run_id>/outage_report.md` |
| P6-3 | Storage pressure handling refuses to silently drop writes when free space falls below the profile threshold and emits the documented operator warning. | synthetic low-space test matches [DEPLOYMENT.md](DEPLOYMENT.md) storage lifecycle contract | `artifacts/recovery/<run_id>/storage_pressure_report.md` |
| P6-4 | Media retention jobs run on the declared schedule and keep the media layout within the profile's retention windows. | zero retention drift over a 24-hour sustained run | `artifacts/recovery/<run_id>/retention_audit.json` |
| P6-5 | Evidence export packaging produces a self-contained export for a selected detection that a reviewer can open without the running system. | export opens cleanly on a second workstation; all referenced media present | `artifacts/recovery/<run_id>/evidence_export_audit.md` |

## Non-functional gates

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| NF-1 | Structured logs from every subsystem land in the declared sink during the acceptance run. | every subsystem in [OPERATIONS_AND_LOGGING.md](OPERATIONS_AND_LOGGING.md) emits at least one structured event per minute under load | `artifacts/ops/<run_id>/log_coverage.json` |
| NF-2 | Secrets and API tokens for deployed profiles are resolved from the deployment profile's secret surface, never committed to git. | pre-ship audit script returns zero findings | `artifacts/ops/<run_id>/secret_scan.json` |
| NF-3 | Remote sync replay against the staging endpoint processes every queued detection and drops zero records. | replay success rate = 1.0 | [SYNC_REMOTE_EVIDENCE.md](SYNC_REMOTE_EVIDENCE.md), `artifacts/ops/<run_id>/sync_replay_report.md` |
| NF-4 | Update and rollback path promotes a new accepted bundle, then rolls back to the prior bundle, preserving runtime stability across both transitions. | two promotion events and one rollback event with zero runtime errors | `artifacts/ops/<run_id>/promotion_rollback_report.md` |
| NF-5 | API-key auth and role mapping hold on the secured deployment profile; unauthenticated calls are refused and audit entries are written. | 100% of unauthorized calls refused; audit log entries match the call set | `artifacts/ops/<run_id>/api_auth_audit.md` |
| NF-6 | Time and timezone on every deployed service match the declared source and stay within tolerance during a 24-hour run. | drift <= 1 second per service | `artifacts/ops/<run_id>/clock_audit.json` |

## Operator readiness gate

| ID | Criterion | Threshold | Evidence |
|---|---|---|---|
| OP-1 | Operator UX pilot ran with the documented participant count and produced scored task outcomes. | >= 5 participants per operator profile; 100% of pilot tasks scored | `artifacts/pilot/<run_id>/scores.csv`, [OPERATOR_UX_PILOT.md](OPERATOR_UX_PILOT.md) |
| OP-2 | Pilot produced zero unresolved show-stopper findings. | 0 show-stoppers open at review | `artifacts/pilot/<run_id>/findings.md` |
| OP-3 | Runbook and handoff documentation cover every operator task the pilot touched. | every pilot task has a runbook entry or a written decision not to document it | `artifacts/pilot/<run_id>/runbook_coverage.md` |
| OP-4 | Field operator training material exists for both dashboard and driver workflows. | materials reviewed and accepted by the operator lead | `docs/OPERATOR_TRAINING.md` (future) |

## Evidence register

Every row must resolve to `accepted` before the review board records a GO decision. Pre-populate new rows when scope is added; never delete rows to clear the register.

| Criterion | Evidence artifact | Owner | Status | Reviewer | Date |
|---|---|---|---|---|---|
| P1-1 | `artifacts/acceptance/<run_id>/long_range_report.md` | ML | pending | | |
| P1-2 | `artifacts/acceptance/<run_id>/long_range_report.md` | Field | pending | | |
| P1-3 | `artifacts/acceptance/<run_id>/plate_pixel_census.json` | Field | pending | | |
| P2-1 | `artifacts/acceptance/<run_id>/low_light_report.md` | ML | pending | | |
| P2-2 | `artifacts/acceptance/<run_id>/low_light_report.md` | Field | pending | | |
| P2-3 | `artifacts/acceptance/<run_id>/preprocess_decision_audit.json` | ML | pending | | |
| P3-1 | `artifacts/bench/edge/<run_id>/edge_bench_report.md` | Edge | pending | | |
| P3-2 | `artifacts/bench/edge/<run_id>/edge_bench_report.json` | Edge | pending | | |
| P3-3 | `artifacts/bench/edge/<run_id>/edge_bench_report.json` | Edge | pending | | |
| P3-4 | `artifacts/recovery/<run_id>/subsystem_kill_matrix.md` | Ops | pending | | |
| P3-5 | `artifacts/recovery/<run_id>/camera_reconnect_report.md` | Ops | pending | | |
| P3-6 | `artifacts/bench/edge/<run_id>/tensorrt_validation.json` | Edge | pending | | |
| P4-1 | `artifacts/acceptance/<run_id>/overall_report.md` | ML | pending | | |
| P4-2 | `artifacts/acceptance/<run_id>/overall_report.md` | ML | pending | | |
| P4-3 | `artifacts/acceptance/<run_id>/ocr_candidate_audit.json` | ML | pending | | |
| P5-1 | `artifacts/acceptance/<run_id>/color_report.md` | ML | pending | | |
| P5-2 | `artifacts/acceptance/<run_id>/make_model_report.md` | ML | pending | | |
| P5-3 | `artifacts/acceptance/<run_id>/year_failure_audit.json` | ML | pending | | |
| P6-1 | `artifacts/acceptance/<run_id>/outage_report.md` | Ops | pending | | |
| P6-2 | `artifacts/acceptance/<run_id>/outage_report.md` | Ops | pending | | |
| P6-3 | `artifacts/recovery/<run_id>/storage_pressure_report.md` | Ops | pending | | |
| P6-4 | `artifacts/recovery/<run_id>/retention_audit.json` | Ops | pending | | |
| P6-5 | `artifacts/recovery/<run_id>/evidence_export_audit.md` | Ops | pending | | |
| NF-1 | `artifacts/ops/<run_id>/log_coverage.json` | Ops | pending | | |
| NF-2 | `artifacts/ops/<run_id>/secret_scan.json` | Ops | pending | | |
| NF-3 | `artifacts/ops/<run_id>/sync_replay_report.md` | Ops | pending | | |
| NF-4 | `artifacts/ops/<run_id>/promotion_rollback_report.md` | Ops | pending | | |
| NF-5 | `artifacts/ops/<run_id>/api_auth_audit.md` | Ops | pending | | |
| NF-6 | `artifacts/ops/<run_id>/clock_audit.json` | Ops | pending | | |
| OP-1 | `artifacts/pilot/<run_id>/scores.csv` | UX | pending | | |
| OP-2 | `artifacts/pilot/<run_id>/findings.md` | UX | pending | | |
| OP-3 | `artifacts/pilot/<run_id>/runbook_coverage.md` | UX | pending | | |
| OP-4 | `docs/OPERATOR_TRAINING.md` | UX | pending | | |

## Open risks

Risks carried into review from existing project state. Mitigations must be in place before a GO decision.

| Risk | Source | Owner | Mitigation | Residual severity |
|---|---|---|---|---|
| CPU workstation mistaken for target-hardware evidence | [EXECUTION_PLAN.md](EXECUTION_PLAN.md) | Edge | Edge bench report must be labeled with device identity; acceptance register only accepts Orin-sourced P3 evidence | medium |
| Synthetic holdouts mistaken for field evidence | [INFERENCE_RUNTIME_EVIDENCE.md](INFERENCE_RUNTIME_EVIDENCE.md) scope boundary | ML | Register only accepts field-captured artifacts for P1-2, P2-2 | medium |
| Legacy training assets bypassing typed manifests | ADR-023 in [DECISIONS.md](DECISIONS.md) | ML | Dataset intake gate enforces typed manifests; no raw folders accepted | low |
| TensorRT bundle validated without real engine execution | ADR-020, ADR-021 in [DECISIONS.md](DECISIONS.md) | Edge | P3-6 requires execution on Orin, not just validation | medium |
| Promoted bundle identity drift across rollback events | ADR-026 in [DECISIONS.md](DECISIONS.md) | Ops | NF-4 exercises a real rollback; external registry is the source of truth | low |
| US-only plate scope misread as general ALPR | ADR-003 in [DECISIONS.md](DECISIONS.md) | Product | Scope section above calls it out; non-US deferred | low |

## Go / no-go decision record

Filled in at the review meeting. Do not backfill.

```
Date:
Participants:
Evidence reviewed:
Criteria accepted:
Criteria rejected:
Open risks accepted:
Conditions (if conditional GO):
Decision: GO | CONDITIONAL GO | NO-GO
Reviewer signatures:
```

A CONDITIONAL GO must carry explicit conditions tied to criterion IDs and a re-review date.

## Review cadence

Re-open this document on every event that could change the register:

- after a new promoted runtime bundle lands
- after a field capture campaign completes
- after the edge bench report updates
- after the operator UX pilot runs
- immediately before any shipping decision

Stale reviews are not reviews. Sign the decision record only against evidence dated within the current review window.

## Gaps found during review design

Items raised while drafting this review that need a home before a GO decision can be recorded:

- `docs/OPERATOR_TRAINING.md` does not yet exist. OP-4 will remain `pending` until it is authored or the criterion is explicitly rewritten.
- No single artifact currently binds the per-criterion field-dataset holdouts to the acceptance run IDs. The acceptance harness (`scripts/acceptance/`) is expected to generate that binding; until it lands, the evidence register rows carry placeholder `<run_id>` tokens.
- Plate pixel density minimum (P1-3) is asserted by [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md) but not numerically. The review board must either publish a number or accept the imaging lead's per-rig measurement as the threshold at review time.
- API auth audit (NF-5) depends on running against the secured deployment profile, not `local-dev`; the secured profile example lives at `configs/deployments/local-secure-api-example.yaml` and example tokens must be replaced before a real audit run.

## Related Documents

- [Requirements](REQUIREMENTS.md)
- [Execution Plan](EXECUTION_PLAN.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
- [Field Eval Qualification](FIELD_EVAL_QUALIFICATION.md)
- [Decisions](DECISIONS.md)
- [Deployment](DEPLOYMENT.md)
- [Operations and Logging](OPERATIONS_AND_LOGGING.md)
- [Inference Runtime Evidence](INFERENCE_RUNTIME_EVIDENCE.md)
- [Promoted Model Benchmarks](PROMOTED_MODEL_BENCHMARKS.md)
- [Sync Remote Evidence](SYNC_REMOTE_EVIDENCE.md)
- [Tracking Fusion Evidence](TRACKING_FUSION_EVIDENCE.md)
- [Preprocessing Benchmark](PREPROCESSING_BENCHMARK.md)
