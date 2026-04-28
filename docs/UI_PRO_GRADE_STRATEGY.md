# UI_PRO_GRADE_STRATEGY.md

RepoScan Pro's operator UI is an in-vehicle recovery console, not a generic analytics dashboard. The interface must reduce operator decision time while preserving verification, audit, and evidence quality.

## Research Inputs

- IACP ALPR operational guidance describes the in-vehicle UI as the place where operators compare the OCR read against the plate crop and larger context image, manage hot lists, handle alert queues, and run reports: https://www.theiacp.org/sites/default/files/all/i-j/IACP_ALPR_Policy_Operational_Guidance.pdf
- IACP guidance also emphasizes that operators must verify the ALPR read and issuing state before acting on a hit. RepoScan should make that verification path visible rather than burying it in detail views.
- Repossession LPR providers emphasize real-time recovery hits, dense scan coverage, historical sightings, and immediate assignment action: https://resolvion.com/services/license-plate-recognition/
- Action-centric dashboard guidance argues for role-specific dashboards with only information essential to the user's action, because extra information undermines actionability: https://www.qualtrics.com/articles/customer-experience/action-centric-dashboard-design/

## Product UI Position

The industry-leading UI for this project should be:

- **Action-first**: every hotlist hit surfaces the next field action immediately.
- **Evidence-led**: plate crop, vehicle overview, OCR alternatives, confidence, camera, time, GPS, and account context stay connected.
- **Verification-safe**: recovery actions are framed around read verification, vehicle match, location confirmation, and account update.
- **Local-first**: the UI remains useful when API sync is degraded, with clear local/demonstration/live state.
- **Low-distraction**: avoid marketing-style cards, oversized decoration, and analytics charts on the driving console.
- **Touch-capable**: primary actions must remain reachable on a laptop touchscreen or small in-cab display.

## First Deployment Scope

The first deployment is a single-operator recovery console. It should not include driver-to-driver coordination, dispatch boards, assigned unit status, en route state, on-scene state, or handoff to another LPR system. Those concepts add screen clutter and belong in a future multi-operator/dispatcher release.

The first deployment should use a smaller recovery state model:

- `active`: a matched account needs operator verification.
- `acknowledged`: the operator has seen the hit and is verifying or routing to the last-seen point.
- `dismissed`: the hit is not actionable right now.
- `recovered`: the account has been completed after verification.
- `false_positive`: the read or vehicle match was rejected.

## Current Design Direction

The console should prioritize, in this order:

1. Active recovery match or selected read.
2. Plate/vehicle identity and verification checklist.
3. Route, inspect, copy tag, and account actions.
4. Live camera/map surface.
5. Live read queue with quick actions.

Search, reporting, account editing, and audit history remain secondary screens.

## Implemented First Deployment Enhancements

- Removed dispatcher, assigned-unit, en route, on-scene, and driver handoff surfaces from the visible operator UI.
- Added a verification gate for OCR, vehicle, account, and location context on recovery cases and alert overlays.
- Added recovery alert keyboard controls for route, confirm, false positive, mute, view record, mark recovered, and dismiss.
- Kept backend assignment contract types available for future compatibility while excluding them from first-deployment screens.

## Recommended Roadmap

- Add a true recovery hit workflow state machine in the UI: `active -> acknowledged -> recovered | dismissed | false_positive`.
- Add a one-screen evidence comparison view optimized for plate crop plus vehicle overview.
- Refine the map as a navigation HUD: route state, distance, ETA, scan radius, active alerts, and layer controls should be visible without covering the target area.
- Add keyboard and hardware-button shortcuts for `route`, `confirm`, `dismiss`, and `mute`.
- Add audible/visual alert policy controls with audit entries for mute/dismiss/false-positive events.
- Add per-account recovery instructions: gate code, tow constraints, safety notes, client-specific restrictions, and contact policy.
- Add operator shift mode with large typography, reduced decoration, and persistent GPS/API/camera status.
- Defer supervisor, dispatcher, unit assignment, and external LPR handoff views until after the first deployment.
- Add usability tests built around timed tasks: acknowledge hit, verify OCR, route to last seen, mark false positive, export evidence, and recover account.

## Acceptance Bar

The UI is professional-grade only when a trained recovery agent can complete these tasks under field conditions without searching:

- identify whether a hit is active, acknowledged, dismissed, or recovered
- compare OCR text with plate crop and full-vehicle context
- route to the last seen point
- open or create the recovery account
- log confirmation, correction, false positive, or dismissal
- export a defensible evidence package
- understand whether the system is live, local-only, or degraded
