# FIELD_CAPTURE_KIT.md

Operator pack for the RepoScan Pro field capture campaign. This kit exists so that when the deployment rig arrives, the field team can execute the missing long-range, low-light, and moving-platform captures in one organized pass and hand the footage off in a form the acceptance harness can consume without rework.

This document is the authoritative shot list and protocol. It does not replace [CAMERA_DEPLOYMENT_WORKFLOW.md](CAMERA_DEPLOYMENT_WORKFLOW.md) for rig registration or [DATASET_INTAKE_WORKFLOW.md](DATASET_INTAKE_WORKFLOW.md) for downstream promotion.

## Prerequisites

Before any capture session:

- the camera is registered per [CAMERA_DEPLOYMENT_WORKFLOW.md](CAMERA_DEPLOYMENT_WORKFLOW.md) §1 and passes `scripts/validate_camera_registry.py`
- the rig has GPS lock and the capture machine clock is synced to the GPS time source
- the dataset workspace exists per [DATASET_INTAKE_WORKFLOW.md](DATASET_INTAKE_WORKFLOW.md) §1
- the capture operator has read [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md) and [ANNOTATION_STANDARDS.md](ANNOTATION_STANDARDS.md) §Lighting And Distance Metadata

## Scene matrix

Every row is a concrete, captureable shot. Session coverage rules come from [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md): every lighting bucket and every range bucket must be covered across at least two capture sessions for the footage to qualify for acceptance use. Scene IDs are used downstream as manifest tags.

### Long-range readability lane (unblocks §12.179)

| Scene ID | Lighting | Range band | Vehicle motion | Platform motion | Target count | Notes |
|---|---|---|---|---|---|---|
| LR-01 | daylight | long_range | stationary | stationary | 1 | baseline standoff shot |
| LR-02 | daylight | long_range | slow roll | stationary | 1 | confirms motion-blur envelope at long range |
| LR-03 | daylight | long_range | highway speed | stationary | 1 | upper bound of target speed |
| LR-04 | daylight | medium | highway speed | stationary | 2+ | multi-target handling |
| LR-05 | dusk | long_range | stationary | stationary | 1 | exposure transition window |
| LR-06 | dusk | long_range | highway speed | stationary | 1 | dusk + motion combo |
| LR-07 | daylight | long_range | stationary | slow platform | 1 | mobile platform at range |
| LR-08 | daylight | long_range | highway speed | slow platform | 1 | worst-case geometry for long range |

### Low-light / no-light lane (unblocks §12.180)

| Scene ID | Lighting | Range band | Vehicle motion | Platform motion | Target count | Notes |
|---|---|---|---|---|---|---|
| LL-01 | night | medium | stationary | stationary | 1 | ambient-light baseline |
| LL-02 | night | medium | slow roll | stationary | 1 | night motion envelope |
| LL-03 | night | long_range | stationary | stationary | 1 | hardest night exercise |
| LL-04 | no_light | medium | stationary | stationary | 1 | no ambient, rig illumination only |
| LL-05 | no_light | medium | slow roll | stationary | 1 | confirms rig illum under motion |
| LL-06 | ir_assisted | medium | stationary | stationary | 1 | IR baseline, hotspot check |
| LL-07 | ir_assisted | medium | slow roll | stationary | 1 | IR motion envelope |
| LL-08 | ir_assisted | long_range | stationary | stationary | 1 | IR long-range stress |
| LL-09 | glare | medium | stationary | stationary | 1 | oncoming headlights at target |
| LL-10 | glare | medium | slow roll | stationary | 1 | headlight glare + motion |
| LL-11 | night | medium | stationary | dark vehicle | 1 | dark body in low contrast |
| LL-12 | night | medium | slow roll | slow platform | 1 | night mobile-platform test |

### Moving-platform lane (unblocks §12.181)

| Scene ID | Lighting | Range band | Vehicle motion | Platform motion | Target count | Notes |
|---|---|---|---|---|---|---|
| MP-01 | daylight | medium | stationary | slow platform | 1 | platform-motion baseline |
| MP-02 | daylight | medium | stationary | highway platform | 1 | highway platform worst case |
| MP-03 | daylight | medium | slow roll | slow platform | 1 | dual motion, aligned |
| MP-04 | daylight | medium | slow roll | slow platform | 1 | dual motion, opposing |
| MP-05 | daylight | medium | highway speed | highway platform | 1 | relative-velocity stress |
| MP-06 | daylight | long_range | stationary | highway platform | 1 | long-range from moving platform |
| MP-07 | night | medium | stationary | slow platform | 1 | night moving platform baseline |
| MP-08 | ir_assisted | medium | stationary | slow platform | 1 | IR moving platform |

### Session coverage rule

Each scene above must be captured in at least two distinct capture sessions on different days or clearly different ambient conditions. A single-day sweep does not qualify for the acceptance register even if every scene ID is checked. This rule comes from [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md) and the `long_range` / `low_light` subset session thresholds documented there.

## Rig checklist

Run the full checklist at the start of every capture day. A missed item invalidates the session for acceptance use.

### Hardware

- primary camera installed and torqued per mount spec
- lens attached, focus locked, focus ring taped
- GPS receiver powered and showing lock
- storage media verified with at least 2x the expected session size free
- capture machine on stable power, fan path clear
- optional IR illuminator (for LL-06 through LL-08) verified warm and aligned
- dash mount (for MP lane) rigidly attached; vibration test with hand
- reference measuring device on board (rangefinder, calibrated cones, or painted lane markers)

### Software

- camera registry validates with no warnings
- capture service reports live frames in headless ingest smoke check
- clock sync confirmed via `w32tm /query /status` on the capture machine
- GPS NMEA stream surfaces in the capture service log
- local media root and staged folders exist with write access
- capture log template open and pre-populated with session ID

### Pre-roll checks

Before the first shot of the day, record a 10-second pre-roll of a static calibration target and confirm:

- focus is correct at the intended standoff distance
- exposure does not hunt when a vehicle enters frame
- GPS latitude and longitude appear in the capture service log
- system clock UTC matches the GPS clock within 1 second
- plate-sized test pattern occupies at least the documented minimum usable pixel count at the intended long-range target (see [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md))

## Per-shot protocol

1. Assign a fresh `shot_id` in the form `<session>-<scene>-<take>` (e.g., `20260501-LR03-02`).
2. Announce scene ID, range, lighting, and motion state verbally if an audio channel exists on the capture device.
3. Roll capture at least 5 seconds before the vehicle enters frame and 5 seconds after it leaves.
4. For moving targets, capture the full traversal without panning the camera.
5. Fill in the capture log row immediately after the shot, while details are fresh. Do not batch log entries at end of day.
6. For uncertain shots, mark the shot as `take_again` in the `notes` column instead of deleting and retrying silently.

## Capture log

Use [capture_log_template.csv](capture_log_template.csv) as the per-shot log. Keep column order stable. One row per take, including discarded takes.

## Safety and legal

- operate only on legally-accessible ground; public-road capture follows local traffic and recording law
- plate privacy: footage is evidence, not content; do not publish, screenshot, or share outside the review workflow
- redact faces and bystander plates that are not relevant to the shot at intake review
- store raw captures under `data/raw/<session_id>/` on the capture machine only; do not copy to external cloud storage; this is consistent with the local-first stance in [REQUIREMENTS.md](REQUIREMENTS.md)
- the capture operator is responsible for immediately stopping capture if asked by a law enforcement officer or property owner

## QA rubric

At end of day, the session reviewer decides whether each shot passes intake. A shot passes only when all of these hold:

- `gt_plate_text` is filled in and matches the visible plate
- the plate is visible in at least one frame per take
- focus is not soft across the full plate
- no severe motion blur that destroys character shape at the range stated in the log
- no exposure blowout on the plate surface
- no rolling-shutter tearing across the plate
- GPS, timestamp, camera ID, and scene ID all appear in the capture metadata
- the scene matches the declared scene ID (lighting, range, motion)
- at least one other take exists for the same scene ID in the session (redundancy)

Shots that fail any rule are marked `rejected` in the log and kept in `data/raw/` but excluded from staging.

Shots that pass are staged per [DATASET_INTAKE_WORKFLOW.md](DATASET_INTAKE_WORKFLOW.md) §5.

## Handoff

When the session is staged:

1. Copy the session folder into `data/staged/<session_id>/` on the workstation that runs the acceptance harness.
2. Place the per-session capture log at `data/staged/<session_id>/capture_log.csv`.
3. Build the scene manifest using the acceptance harness manifest tool (see [ACCEPTANCE_HARNESS.md](ACCEPTANCE_HARNESS.md)). The manifest output path by convention is `data/manifests/field/<session_id>.yaml`.
4. Run the qualification gate per [FIELD_EVAL_QUALIFICATION.md](FIELD_EVAL_QUALIFICATION.md) against the manifest and retain the qualification report next to the manifest.
5. Promote only qualified sessions into `data/eval/field/<session_id>/` so acceptance runs consume protected holdouts.

The acceptance harness output will land in `artifacts/acceptance/<run_id>/` as declared in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) evidence register.

## Failure modes to watch

Field-observable failure modes, ranked by how often they invalidate a shot. Each comes with the field mitigation the operator can apply during the day.

| Failure mode | Symptom | Mitigation |
|---|---|---|
| Motion blur at long range | smeared characters along motion axis even when stationary target | raise shutter speed; stop down and raise ISO before accepting blur |
| Rolling-shutter tearing | slanted or torn plate characters on fast-moving targets | switch to a global-shutter mode if available; slow the platform if the shot allows |
| Exposure hunting | auto-exposure oscillates as vehicle enters frame | lock exposure to the expected plate luminance before the shot |
| Headlight bloom | plate washed by retroreflective bloom at night | tilt mount slightly off-axis; verify angle of incidence |
| IR hotspot blowout | center of plate saturated under rig illumination | increase illuminator distance; diffuse illuminator; verify hotspot footprint |
| Windshield reflection | rig interior visible on vehicle glass | add polarizing filter; adjust mount angle |
| Plate saturation | plate characters clipped to white | lock exposure; lower gain; confirm with histogram |
| Vibration blur | periodic blur at idle or under engine vibration | tighten mount; add vibration dampener; re-run mount torque check |
| Focus drift | focus soft after temperature change | re-lock focus at start of each session and mid-session after temperature change |
| GPS dropout | NMEA gap or stale timestamp | pause capture; confirm GPS lock; do not resume until lock returns |
| Clock drift | system clock diverges from GPS | re-sync clock; mark affected shots for re-take |

## Requirements traceability

Every scene ID above traces back to a specific checklist or requirement item:

- `LR-*` rows trace to [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) §2.35, §12.179, and the long-range priority in [REQUIREMENTS.md](REQUIREMENTS.md)
- `LL-*` rows trace to [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) §2.36, §12.180, and the low-light priority in [REQUIREMENTS.md](REQUIREMENTS.md) and [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md)
- `MP-*` rows trace to [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) §12.181 and the moving-platform requirement in [REQUIREMENTS.md](REQUIREMENTS.md)

## Gaps noted during kit authoring

Items the existing docs do not yet numerically commit, which the operator will have to resolve at rig setup:

- minimum usable plate pixel count at the long-range target is asserted qualitatively in [CAMERA_AND_IMAGING.md](CAMERA_AND_IMAGING.md) but not quantified; the imaging lead must publish the number or accept the per-rig measurement as the threshold (also called out in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) gaps section)
- the moving-platform lane has no documented maximum safe operating speed; the field team must set a number before MP-05 or MP-06 run
- rig illuminator spec for LL-04 and LL-05 is not documented; the operator must record the illuminator used in the `notes` column of the capture log so it can be tied back to the shot at review time

## Related Documents

- [Camera And Imaging](CAMERA_AND_IMAGING.md)
- [Camera Deployment Workflow](CAMERA_DEPLOYMENT_WORKFLOW.md)
- [Dataset Intake Workflow](DATASET_INTAKE_WORKFLOW.md)
- [Field Eval Qualification](FIELD_EVAL_QUALIFICATION.md)
- [Annotation Standards](ANNOTATION_STANDARDS.md)
- [Requirements](REQUIREMENTS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
- [Production Readiness](PRODUCTION_READINESS.md)
