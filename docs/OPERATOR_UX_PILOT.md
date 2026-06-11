# OPERATOR_UX_PILOT.md

Executable pilot plan for validating the RepoScan Pro operator experience against field-adjacent users. This document is the source of truth the UX pilot runs from. Its output feeds criterion OP-1 through OP-4 in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) and closes [PROJECT_STATUS_CHECKLIST.md](PROJECT_STATUS_CHECKLIST.md) §12.184.

The pilot does not require hardware. It runs against the headless demo runtime with local storage and seeded data.

## Goal and hypotheses

Goal: confirm the current operator UI supports the full review and response loop an operator would run during a real shift, and surface any friction that would cost real time or cause a missed alert in the field.

Working hypotheses:

- operators can triage a live hotlist alert from appearance in the activity stream to a confirmed review decision without leaving the main console.
- operators can search for a prior plate and open the matching detection detail in under 30 seconds.
- operators can manage an active hotlist edit without losing their current alert selection.
- operators can drive the route planner to a destination using a known address with no prior training.
- operators can hand off a pinned follow-up to another session or acknowledge one from another session.

A result that contradicts any hypothesis is a pilot finding that feeds the analysis plan below and, if severe enough, blocks the production-readiness review at criterion OP-2.

## Participants

Target profile: practicing operators who have done live plate monitoring or vehicle recovery dispatch work. Two operator profiles are in scope:

- dashboard operator (desk, multi-camera, hotlist triage)
- driver operator (in-vehicle, driver mobile surface, recovery workflow)

Minimum count: 5 participants per profile (10 total). This matches the threshold in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) OP-1.

Selection criteria: at least 6 months of operational experience, a mix of comfort levels with digital tooling (do not select only power users), and no prior exposure to RepoScan Pro.

Consent posture: written consent to observe, record screen (not face), and store notes for review purposes. No recording leaves the local workstation without explicit re-consent. Consent form template lives next to this document at review time; keep a signed copy in `artifacts/pilot/<run_id>/consent/`.

## Test environment

- local workstation running the `local-dev` deployment profile
- headless demo runtime started through the UI control surface
- seeded detection, hotlist, and alert data via the existing development seed path
- no live camera
- single observer station beside the participant
- capture the screen recording to `artifacts/pilot/<run_id>/recordings/<participant_id>.mp4` if the workstation supports it; fall back to observer notes if not
- keep a second idle session logged in to demonstrate the dispatch and multi-session tasks

Verify the environment from the readiness checklist at the bottom of this document before any participant arrives.

## Task script

Each task has: pre-state, operator-facing instructions, success criteria, and observer notes prompts. The observer reads instructions verbatim. Success is binary per task (`completed` / `partial` / `failed` / `abandoned`); severity is scored separately.

### Task 1 — Triage a live hotlist alert

- Pre-state: headless demo runtime running, seeded hotlist with at least one vehicle that will match a detection in the next 60 seconds, activity stream empty.
- Instructions: "You are monitoring the console. A new alert will appear. Respond to it the way you would on shift."
- Success criteria: operator notices the alert within 10 seconds of appearance, opens the matching detection detail, reviews the plate crop and alternate OCR candidates, and records an acknowledgement or stand-down decision with a note.
- Observer prompts: did the alert draw attention without prompting? which affordance did the operator reach for first? did they find the alternate OCR candidates on their own?

### Task 2 — Investigate a prior plate read

- Pre-state: activity stream populated with the last 10 minutes of demo traffic.
- Instructions: "You need to find the most recent read of plate ABC1234. Open its detection detail."
- Success criteria: operator enters search mode, enters the plate (full or partial), and opens the correct detection detail in under 30 seconds.
- Observer prompts: did the search surface find them or did they hunt? did partial-plate search appear obvious?

### Task 3 — Manage a hotlist entry while holding a selection

- Pre-state: operator has task 2's detection detail open.
- Instructions: "Add plate XYZ7777 to the current hotlist, then return to the detection you were just viewing."
- Success criteria: the hotlist add completes without closing or reloading the selected detection; the operator finds their way back to the prior selection.
- Observer prompts: did the selection survive the hotlist edit? did the operator think they had lost their place?

### Task 4 — Pin a follow-up and hand it off

- Pre-state: a detection of interest is visible in the activity stream.
- Instructions: "Pin this detection for follow-up. Assign it to yourself with a one-line note. Then imagine another operator is taking it over and re-assign it."
- Success criteria: pin is persisted; assignment and note are persisted; reassignment updates the follow-up owner visibly.
- Observer prompts: did "pin" and "assign" feel like one concept or two? was the reassignment path discoverable?

### Task 5 — Drive the route planner to a known address

- Pre-state: driver mobile surface open on the console; GPS in demo mode.
- Instructions: "Open the route planner and set a destination at a local address you know. Start navigation."
- Success criteria: address autocomplete works, route renders, navigation state activates, map controls stay usable with the route loaded.
- Observer prompts: did the address autocomplete surface the right result? was the destination modal obvious? did the map controls obstruct the route after start?

### Task 6 — Recovery account intake

- Pre-state: operator is in the recovery account workspace.
- Instructions: "Create a recovery account for a vehicle we only know by VIN and general description. Attach an intended recovery address."
- Success criteria: recovery account persists; intake-only state is clear; the account does not silently promote to live alerting.
- Observer prompts: was the intake-only versus live-alerting distinction clear? was address intake in the account workflow consistent with the route planner address experience?

### Task 7 — Respond to an alert in a multi-session environment

- Pre-state: two sessions logged in on the same console; a new alert about to fire.
- Instructions: "When the alert fires, acknowledge it. Then check whether the other session saw it acknowledged."
- Success criteria: acknowledgement persists; the second session sees an up-to-date status within 10 seconds; no ghost-state in either session.
- Observer prompts: did the operator trust the multi-session state? did the other session require a refresh?

### Task 8 — Export evidence for handoff

- Pre-state: a detection with media is selected.
- Instructions: "Export the evidence for this detection in a form you could hand off to a colleague who does not have the system running."
- Success criteria: the export completes and is discoverable in the filesystem; the operator can describe how to share it without guidance.
- Observer prompts: was the export location obvious? was the operator confident they had everything needed for the handoff?

### Task 9 — Recover from an outage condition

- Pre-state: observer triggers a simulated network outage on the workstation before this task (block the sync transport; leave local capture and inference running).
- Instructions: "Continue monitoring. You will notice a connectivity issue. Describe what you would do and continue working the activity stream."
- Success criteria: operator notices a degraded-state indicator, continues to triage and persist local decisions, and does not lose confidence that local work is being preserved.
- Observer prompts: was degraded state visible? did the operator hesitate to continue recording decisions locally?

### Task 10 — Debrief and self-report

- Pre-state: all prior tasks complete.
- Instructions: "Walk me through what you would change about this interface before you used it on shift."
- Success criteria: operator can produce at least three ranked suggestions.
- Observer prompts: capture verbatim; tag each suggestion with its severity from the rubric below.

## Scoring rubric

Outcome (per task):

- `completed`: success criteria fully met without prompting
- `partial`: success criteria met with observer clarification or after clear struggle
- `failed`: success criteria not met within the time window
- `abandoned`: participant stopped or asked to skip

Time-on-task is captured in seconds from the moment the operator receives the instruction to the moment the observer scores the outcome. Errors is a count of wrong-path actions (wrong click, wrong surface, hunt-and-peck).

Severity (per finding):

- `show-stopper`: a field operator would miss an alert, lose evidence, or make a wrong decision because of this
- `friction`: noticeably slows the operator but does not break correctness
- `polish`: visual or copy issue with no correctness impact
- `nice-to-have`: suggestion for a future iteration

Any `show-stopper` finding blocks the production-readiness review at criterion OP-2 until resolved or explicitly accepted with a written exception.

## Data collection template

Observers fill in [operator_pilot_scoring_template.csv](operator_pilot_scoring_template.csv) live, one row per task per participant. Free-form observer notes go in the `observer_notes` column and should be short phrases, not narrative. A separate row captures the debrief suggestions from task 10, with `task_id = "debrief"` and one row per suggestion.

## Debrief protocol

Five minutes max per participant, verbal, captured as short observer notes.

1. Which part of the task script felt most wrong for how you would actually work?
2. Was there a moment you thought you had lost data or state?
3. Was there a moment you were not sure the system was working?
4. If you could change one thing before your next shift, what would it be?
5. Any behavior you expected that we did not ask you to do?

## Analysis plan

After all sessions complete:

1. Compute per-task completion rate and median time-on-task across both operator profiles.
2. List every `show-stopper` finding with the tasks it was observed on.
3. List every `friction` finding with frequency.
4. Roll the findings into `artifacts/pilot/<run_id>/findings.md`, ordered by severity.
5. For every `show-stopper`, open a follow-up issue with acceptance criteria drawn from the failing task.
6. Produce `artifacts/pilot/<run_id>/scores.csv` from the scoring template.
7. Record pilot outcome against OP-1 through OP-4 in the [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) evidence register.

## Dry-run readiness checklist

Verify all of these before inviting the first real participant. A failure on any line blocks the pilot from starting.

- [ ] `local-dev` deployment profile starts cleanly with `scripts/check.ps1` (or platform equivalent) returning green
- [ ] `npm run ui:build` completes without errors
- [ ] UI shell loads in the supported browser with no console errors on the default workspace layout
- [ ] Headless demo runtime starts from the UI control surface and the activity stream begins populating within 60 seconds
- [ ] Seeded hotlist contains at least one entry matching a vehicle in the demo stream
- [ ] A screen recorder is configured and writes to `artifacts/pilot/<run_id>/recordings/` (or observer notes fallback is prepared)
- [ ] Two operator sessions can log in on the same console
- [ ] Network partition simulation for task 9 is prepared and documented in the observer packet
- [ ] Signed consent form template is on the workstation
- [ ] Observer has a printed or screen copy of the task script and scoring template

## Known issues for pilot prep

This section is filled in during dry-run and updated every time the pilot is re-run. It carries items that are not show-stoppers for a real run but which the observer should know about so dry-run friction does not contaminate real participant scoring.

Dry-run was not executed during initial pilot plan authoring. The first real dry-run must be completed and its findings logged here before the first participant session. If the UI cannot be brought up quickly, that is itself a show-stopper and the pilot must be postponed until the UI shell starts cleanly from the dry-run checklist above.

Known fragile areas to exercise during dry-run (drawn from recent commit history and [MAP_NAVIGATION_REDESIGN.md](MAP_NAVIGATION_REDESIGN.md)):

- map/route planner interaction with leaflet panes (task 5) has had multiple recent fixes; confirm route controls sit above the map after start-navigation
- address autocomplete depends on the API proxy (task 5 and task 6); confirm the proxy reaches its backing service on the dry-run workstation
- recovery account intake surface (task 6) is a relatively recent split-out; confirm intake-only state is still visually distinct

## Related Documents

- [Requirements](REQUIREMENTS.md)
- [Product](PRODUCT.md)
- [UI Workflows](UI_WORKFLOWS.md)
- [UI Competitive Alignment](UI_COMPETITIVE_ALIGNMENT.md)
- [Driver Mobile UI Wireframe Spec](DRIVER_MOBILE_UI_WIREFRAME_SPEC.md)
- [Map Navigation Redesign](MAP_NAVIGATION_REDESIGN.md)
- [Production Readiness](PRODUCTION_READINESS.md)
- [Project Status Checklist](PROJECT_STATUS_CHECKLIST.md)
