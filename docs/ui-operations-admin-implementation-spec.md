# RepoScan UI Operations/Admin Redesign Implementation Spec

## Purpose

This document translates the current `apps/ui` product into a deployable two-area product structure:

1. `Operations Workspace`
2. `Admin Panel`

It is written against the current codebase and API contracts, not a greenfield system. The intent is to improve clarity, field usability, and future scalability without breaking current map, LPR, alert, hotlist, follow-up, camera, or settings behavior.

## Current Repo Baseline

### Active frontend
- App entry: `apps/ui/src/App.tsx`
- API contracts: `apps/ui/src/live-api.ts`
- Current top-level screens:
  - `console`
  - `search`
  - `accounts`
  - `hotlists`
  - `settings`

### Existing backend-backed or frontend-meaningful records
- `DashboardDetection`: live read / LPR detection record
- `DashboardAlert`: recovery match / alert event
- `DashboardHotlist`: current account/watch record combining plate, vehicle, address, label, and notes
- `FollowUpRecord`: action queue / case follow-up
- `ApiAuditEvent`: audit history
- `OperatorPrincipal` / `OperatorSessionRecord`: user and session context

### Current workflow reality
- `console` is the live field workspace
- `search` is the investigation and record lookup workspace
- `accounts` is the current recovery account / hotlist management screen
- `hotlists` is the current recovery queue and recognition activity screen
- `settings` mixes operator settings, system health, audit, edge runtime controls, and permissions

## Product Direction

The UI should become two clearly separated but connected shells:

### A. Operations Workspace
Purpose:
- Active field work
- Route decisions
- LPR triage
- Recovery opportunity review
- Current target review

Primary user questions:
- What needs action now?
- Where is it?
- How strong is the signal?
- What should I do next?
- What do I need to avoid or verify before acting?

### B. Admin Panel
Purpose:
- Repo order management
- Data quality
- Record editing
- Imports/exports
- Settings and audit
- Future user/team administration

Primary user questions:
- What records exist?
- Which orders are active?
- What data is missing or duplicated?
- What changed and who changed it?
- What defaults and operational settings govern the system?

## Why Two Shells

The current product already hints at two different modes of use:

- The `console` and `hotlists` screens are action-oriented.
- The `accounts` and parts of `settings` are management-oriented.

Combining both into a single dashboard creates three problems:

1. Field tasks compete visually with data-entry tasks.
2. Long-form editing pushes critical map and hit context off the screen.
3. The product feels like a mixed tool instead of a dedicated recovery workspace.

Separating `Operations` from `Admin` solves this immediately while preserving cross-links between them.

## Recommended Information Architecture

### Shell-level navigation
- `Operations`
- `Admin`

### Operations navigation
- `Workspace`
- `Map`
- `LPR Hits`
- `Search`
- `Active Orders`

### Admin navigation
- `Repo Orders`
- `Vehicles`
- `Addresses`
- `Accounts`
- `Imports / Exports`
- `Audit`
- `Settings`

### Recommended route model

Operations:
- `/ops/workspace`
- `/ops/map`
- `/ops/hits`
- `/ops/search`
- `/ops/orders`
- `/ops/orders/:orderId`

Admin:
- `/admin/orders`
- `/admin/orders/new`
- `/admin/orders/:orderId`
- `/admin/vehicles`
- `/admin/vehicles/:vehicleId`
- `/admin/addresses`
- `/admin/addresses/:addressId`
- `/admin/accounts`
- `/admin/accounts/:accountId`
- `/admin/imports`
- `/admin/audit`
- `/admin/settings`

For the current codebase, these do not need to become true URL routes immediately. They can begin as shell-level internal state and later move to proper routing.

## Mapping Current Screens To Future Structure

### `console` -> `Operations / Workspace`
Keep and refine as the main field workspace.

### `search` -> `Operations / Search`
Keep as a focused investigation screen for detections, sightings, and lead review.

### `hotlists` -> split into:
- `Operations / LPR Hits`
- `Operations / Recovery Queue`

The queue and recognition activity already belong in Operations, not Admin.

### `accounts` -> `Admin / Repo Orders` and `Admin / Accounts`
The current screen is a hybrid of watchlist setup and order/account setup. It should evolve into a record-management surface inside Admin.

### `settings` -> split into:
- `Operations preferences` for field behavior
- `Admin / Settings` for system, data retention, labels, audit visibility, edge runtime, and integration settings

## Core UX Rule

The Operations shell should optimize for:
- triage
- route
- verify
- note
- update status

The Admin shell should optimize for:
- create
- edit
- organize
- validate
- audit

Full record editing should not be a first-class behavior inside the Operations workspace.

## Operations Workspace Specification

### Layout model

Desktop:
- Center hero: map and route
- Left rail: active orders and priority hits
- Right rail: selected order / account / address context
- Bottom band: recent detections, route summary, next action, warnings

Tablet:
- Map first
- Slide-over queue
- Bottom sheet for address and order context

Mobile:
- One primary module at a time
- Map or current alert first
- Bottom nav with quick actions

### Required modules

#### 1. Active Orders rail
Shows:
- active repo orders
- priority
- status
- target plate / vehicle
- last seen
- next scheduled action or due follow-up

Recommended actions:
- open quick view
- route
- mark watch
- mark complete
- push to Admin detail

#### 2. Map hero
Shows:
- current position
- active target pins
- known addresses
- last-seen detections
- route line
- ETA / distance
- approach cues

#### 3. Priority LPR Hits panel
Shows:
- new match
- exact vs normalized match
- confidence
- linked order
- alert age
- acknowledge / stand down / reopen

#### 4. Vehicle / Account quick view
Shows:
- plate / VIN / year / make / model / color
- debtor/account name
- client/lienholder
- order priority
- order status
- linked addresses count
- last seen
- open follow-up

#### 5. Address intelligence panel
Shows:
- primary address
- alternate addresses
- confidence score
- source
- last verified
- parking or access notes
- risk flags
- prior recovery history summary
- best approach recommendation

#### 6. Route tools
Shows:
- destination
- route distance
- ETA
- route mode
- quick re-route options
- set next stop

#### 7. Recent detections
Shows:
- latest reads tied to active work
- compact snapshots
- confidence
- location
- time

#### 8. Next-best-action panel
Recommended logic:
- If new critical hit exists: `Review hit now`
- If acknowledged hit lacks route: `Route to last seen`
- If active order lacks verified address: `Review address intel`
- If follow-up is overdue: `Resolve overdue follow-up`
- If no active hit but high-priority order exists: `Stage next address`

#### 9. Compliance / risk warnings
Shows:
- gate / camera flags
- unsafe approach notes
- stale address confidence
- missing plate/VIN confidence
- client hold / pause

### Operations summary logic

The main workspace should rank attention using a visible priority stack:

`order priority + alert state + confidence + recency + follow-up due + risk flag presence`

This keeps the single-user operator focused on one clear next action.

## Admin Panel Specification

## Repo Orders

Purpose:
- central operational business record

List view columns:
- order number
- priority
- status
- debtor/account
- client/lienholder
- primary vehicle summary
- primary plate
- city/state
- last activity
- assigned owner

List actions:
- new order
- filter
- bulk archive
- export filtered set

Detail view tabs:
- `Overview`
- `Vehicle`
- `Addresses`
- `Contacts`
- `Documents`
- `Notes`
- `Sightings`
- `History`

Required functions:
- add
- edit
- archive
- delete
- status change
- attach docs/images
- add notes
- link plates, VINs, vehicles, addresses, contacts
- mark priority
- track history

## Vehicle Records

List view:
- VIN
- plate(s)
- year/make/model
- color
- linked order count
- last sighting
- status

Detail fields:
- VIN
- primary plate
- alt plates
- make
- model
- year
- color
- identifiers / damage / decals
- image references
- linked sightings
- vehicle status

## Address Records

List view:
- label
- address
- type
- confidence
- source
- last verified
- linked orders
- risk flags

Detail fields:
- primary / alternate addresses
- confidence score
- source
- last verified date
- notes
- risk flags
- prior recovery history
- navigation shortcut

## Account / Customer Records

List view:
- debtor/account name
- client/lienholder
- status
- linked orders
- last updated

Detail fields:
- debtor/account
- lienholder/client
- contact methods
- recovery priority
- notes
- documents
- linked orders

## Imports / Exports

Import flow:
1. upload CSV/spreadsheet
2. detect columns
3. map columns to fields
4. validate rows
5. show duplicates/conflicts
6. confirm import

Validation rules:
- plate normalization
- VIN length check
- required client/order/account keys
- duplicate order number detection
- duplicate vehicle key warning
- bad address confidence flag

## System Settings

Split into groups:
- `LPR`
- `Alerts`
- `Map`
- `Data Retention`
- `Order Defaults`
- `Priority Labels`
- `Integrations`
- `Users / Teams` later

## Audit / Activity

Track:
- order created
- order edited
- order archived / deleted
- status changed
- note added
- document attached
- hit linked to order
- address intel updated

## Single-user now / multi-user later

In version one:
- the current operator performs all actions
- ownership fields can default to the current principal
- audit still records actor and timestamps

Later:
- admin, agent, dispatcher, manager, and client views can sit on the same structure

## Repo Order Data Model Recommendation

### Current backend reality

Today, `DashboardHotlist` is carrying several concepts at once:
- plate/VIN watch key
- vehicle details
- address details
- label
- notes
- active state

That is useful for v1 compatibility, but not ideal long-term.

### Recommended business model

Introduce a dedicated `RepoOrder` concept above current hotlist and follow-up records.

Recommended entities:
- `RepoOrder`
- `VehicleRecord`
- `AddressRecord`
- `AccountRecord`
- `OrderDocument`
- `OrderNote`
- `OrderHistoryEvent`

### Recommended relationships
- one account can have many repo orders
- one repo order can link to one or more vehicles
- one repo order can link to one or more addresses
- one vehicle can have many historical sightings
- one order can generate many LPR hits
- one hit can optionally resolve into a follow-up

### Suggested status model
- `new`
- `ready`
- `active`
- `watch`
- `on_hold`
- `completed`
- `cancelled`
- `archived`

### Suggested priority model
- `low`
- `standard`
- `high`
- `critical`

## Repo Order Workflow

### Create order
1. Create order record
2. Add client/lienholder
3. Add debtor/account
4. Add vehicle
5. Add primary search keys
6. Add addresses
7. Add risk and field notes
8. Set priority
9. Activate

### Required fields
- order reference / external order number
- client/lienholder
- debtor/account name
- status
- priority
- at least one vehicle search key:
  - primary plate
  - VIN
- one recovery posture:
  - verified primary address
  - alternate address only
  - intelligence pending

### Optional fields
- alt plates
- vehicle color
- identifiers
- balance / recovery value
- contacts
- documents
- risk notes
- best time windows
- neighborhood notes
- gate / garage / camera notes

### Validation rules
- normalize plate formatting
- uppercase VIN and validate structure when possible
- warn on duplicate VIN
- warn on duplicate client + plate combination
- warn on address confidence below threshold
- prevent activation if no valid search key exists
- require terminal reason for completed/cancelled

### Close / archive flow
- completed or cancelled orders move out of Operations
- archived orders remain searchable in Admin
- deleted orders should be exceptional and audited

## Admin-to-Operations Data Flow

### What should feed Operations
- active repo orders
- linked vehicle search keys
- linked addresses
- priority
- notes
- risk flags
- latest status
- linked documents summary if relevant

### How existing contracts can support v1

#### Use current `DashboardHotlist` as:
- the watchable vehicle/order target record for matching

#### Use current `FollowUpRecord` as:
- the operational next-step / assignment / due-action record

#### Use current `DashboardAlert` as:
- the live recovery hit event

### Recommended v1 UI strategy

Do not wait for a perfect backend redesign to ship the better UI.

Ship `Repo Orders` in the Admin UI as a composite abstraction:
- one visible order detail
- backed by the current hotlist record
- enriched by follow-ups
- enriched by detections/alerts
- later upgraded to a dedicated order contract

This preserves current backend compatibility while giving the user the right mental model now.

## What Must Stay Out Of The Operations Dashboard

Move to Admin or secondary drawers:
- bulk order management
- full account editing
- import/export tooling
- long-form tables
- audit history
- data cleanup
- duplicate resolution
- system configuration
- archive management

Keep in Operations:
- map
- active queue
- selected order
- current hit
- route
- recent detections
- address intel
- warnings

## Layout Recommendations

## Desktop

Best for:
- admin work
- order detail review
- audit and imports
- full-side-by-side operations

Visible first:
- in Operations: map, active queue, selected order context
- in Admin: list, filters, detail drawer

Collapsible:
- recent detections
- alt addresses
- notes
- history

Hide until requested:
- imports
- bulk tools
- audit details

## Tablet

Best for:
- map work
- quick admin review
- field triage

Visible first:
- map
- active orders
- hit details

Collapsible:
- order context
- address intel
- recent detections

Hide until requested:
- full edit forms
- import tools
- audit

## Mobile

Best for:
- alerts
- quick checks
- route actions
- status changes

Visible first:
- current top-priority order or hit
- map / route
- next action

Collapsible:
- address intel
- notes
- recent detections

Hide until requested:
- full admin editing
- long tables
- audit log

## Future Multi-User Expansion

Build these assumptions into the structure now:
- every major record supports `created_by`, `updated_by`, and optional `assigned_to`
- every order supports an owner / assignee
- every status change is auditable
- every screen can respect capability flags
- Operations and Admin are separate shells with role-aware access later

Future roles:
- `Admin`
- `Field Agent`
- `Dispatcher`
- `Manager`
- `Client / Lienholder`

The current `OperatorPrincipal.roles` and `capabilities` model in `live-api.ts` is the correct starting point for this.

## Recommended Implementation Plan For This Repo

### Phase 1: Information architecture and labels
- Add explicit shell concept: `Operations` vs `Admin`
- Rename user-facing copy:
  - `console` -> `Operations`
  - `search` -> `Search`
  - `accounts` -> `Repo Orders`
  - `hotlists` -> `Recovery Queue`
  - `settings` -> `Settings`
- Keep current internals intact

### Phase 2: Operations shell refinement
- Keep existing map-first console
- Make active orders and LPR hits first-class panels
- Reduce management-only actions in field view
- Surface next-best-action and risk more clearly

### Phase 3: Admin shell introduction
- Convert current `accounts` screen into `Admin / Repo Orders`
- Split form into order, vehicle, address, and notes sections
- Add list/detail workflow instead of one long mixed editor

### Phase 4: Settings and audit separation
- Move operator preferences to Operations-friendly settings
- Move system, audit, edge runtime, import defaults, and future user config into Admin settings

### Phase 5: Backend-aligned order model
- Introduce a true `RepoOrder` contract when backend timing allows
- Keep compatibility layer from current `DashboardHotlist` until then

## File-Level Implementation Direction

Near-term likely files:
- `apps/ui/src/App.tsx`
- `apps/ui/src/live-api.ts`
- `apps/ui/src/dashboard.css`
- `apps/ui/src/styles.css`
- `apps/ui/src/components/dashboard/*`

Recommended next extraction targets:
- `OperationsShell`
- `AdminShell`
- `RepoOrdersList`
- `RepoOrderDetail`
- `VehicleRecordPanel`
- `AddressRecordPanel`
- `OrderHistoryPanel`
- `ImportWizard`

## Final Recommendation

Treat the product as two connected systems:

1. `Operations Workspace`
   - fast
   - map-first
   - action-oriented
   - minimal editing
   - built around active repo orders, LPR hits, and route decisions

2. `Admin Panel`
   - structured
   - table/detail driven
   - record-oriented
   - built around repo orders, vehicles, addresses, accounts, imports, audit, and settings

For v1, keep backend compatibility by presenting a `Repo Order` UI abstraction over the existing hotlist/follow-up/alert model. For v2, add a dedicated order contract without changing the shell structure.

This gives the product a professional operating model now while preserving a clean path to multi-user deployment later.
