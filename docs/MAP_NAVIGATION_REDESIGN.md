# Map And Navigation Redesign

## Purpose

Define the full map and navigation redesign for RepoScan Pro before implementation so the work lands as one coherent operator workflow, not a series of disconnected map fixes.

This document complements [UI_COMPETITIVE_ALIGNMENT.md](UI_COMPETITIVE_ALIGNMENT.md) and focuses on:

- in-map destination workflow
- offline mapping and offline routing
- alert and historical-hit visibility during navigation and idle map use
- radius and auto-scan controls
- backend contracts required to support the UI cleanly

## System Goal

The map is not just a visual aid. In a repossession workflow it must do four jobs at once:

1. Show where the unit is in relation to the target and recent evidence.
2. Let the operator set or change destination fast without leaving the map.
3. Keep prior alerts and sightings visible so the operator can reason about pattern, not just the current route.
4. Arm and control radius-based auto-scan without forcing the operator into a settings screen.

If the map cannot do all four, it is not meeting the operational requirement.

## Operator Requirements

The final map and navigation system must support these operator tasks:

1. Open the map with no active route and still see useful operational context.
2. Set a destination from:
   - manual address input
   - a hotlist/account address
   - an alert location
   - a detection location
   - a previous destination from recents
3. Preview a route before committing to navigation.
4. Start navigation without losing alert visibility.
5. Keep previous alerts and sightings visible while navigating.
6. Toggle alert layers on or off without leaving the map.
7. Filter visible alerts by status and time window.
8. Adjust radius and auto-scan directly from the map.
9. Keep the map useful even when navigation is idle.
10. Persist route and map state across refresh and operator session heartbeat.

## Current Gaps

The current implementation in [App.tsx](../apps/ui/src/App.tsx) has a functional shell but it is not yet production-grade for repossession work:

- destination input lives in the left rail instead of the map surface
- radius is controlled through settings instead of map controls
- the map uses online OpenStreetMap tiles
- navigation is simulated UI state, not true routed navigation
- previous alerts are not treated as a persistent map layer system
- layer toggles and alert filters are not operator-first controls

## Final UX Model

### Primary Map Surface

The map becomes a first-class workspace, not a passive panel.

Map chrome should include:

- top-left route status chip
- top-right map tools button group
- bottom-center navigation dock
- optional right-side collapsible route and alert drawer

### Destination Entry

Destination input moves into the map workflow.

Primary interaction:

- `Set Destination` CTA inside the map header or top tool rail
- opens a route modal over the map
- operator enters address or chooses a suggested source
- route preview appears before activation
- operator confirms route
- modal closes and active route card remains on map

The old left-rail destination card should be removed after parity is reached.

### Route Modal

The route modal should support:

- free-form address search
- structured address entry when needed
- recent destinations
- account-linked addresses
- last alert location
- last detection location
- one-click "Route to latest confirmed sighting"

The modal should show:

- destination label
- geocoded address
- ETA
- distance
- route summary
- confirm and cancel actions

### Bottom Navigation Dock

The map must expose the high-frequency controls in one place.

Recommended dock items:

- `Destination`
- `Scan`
- `Recenter`
- `Alert Layers`
- `End Route`

The radius control is no longer a dock item. It belongs in map settings as a configurable behavior default.

### Scan Behavior

Navigation and idle scanning should behave differently.

Rules:

- when a destination is active, arrival auto-scan is enabled by default
- the default arrival trigger distance is `50 ft`
- the operator does not need to manually arm scanning each time they route to an address
- entering the arrival radius changes the route chip state to `IN RADIUS - AUTO SCAN`
- when not navigating, scanning can be turned on or off from a dashboard CTA
- the dashboard CTA controls idle scanning only
- arrival-radius behavior is configured in settings, not controlled from the map dock

### Alert Visibility

Previous alerts and hits must stay visible on the map whether navigation is active or idle.

This is required behavior, not optional polish.

The map needs alert layers for:

- active alerts
- acknowledged alerts
- dismissed alerts
- recent detections
- assigned destinations
- hotlist/account addresses

Default behavior:

- active alerts on
- acknowledged alerts on
- dismissed alerts off
- recent detections on
- destination on
- route on when navigation is active

### Alert Layer Controls

Alert map icons must be toggleable from the map itself and also configurable in settings.

Two control surfaces are required:

1. Map toolbar or dock icon for quick operator toggles.
2. Map settings section for persistent defaults.

Quick toolbar control should support:

- show or hide all alert pins
- show or hide active alerts
- show or hide historical alerts
- show or hide recent detections
- show or hide destination and radius ring

Settings page should support persistent defaults for:

- default visible layers
- default time window for historical alerts
- default icon density and clustering
- arrival auto-scan radius
- arrival auto-scan default on or off
- auto-center behavior

## Map States

The map should have explicit states:

1. `idle`
   No active route. Alerts and detections still visible.
2. `route_preview`
   Destination chosen, route visible, not yet started.
3. `navigating`
   Route active, ETA and distance live, alerts still visible.
4. `in_radius`
   Unit has entered arrival radius.
5. `arrived`
   Destination reached or operator marks route resolved.
6. `manual_browse`
   Operator is panning or inspecting overlays without follow mode.

## Required Overlays

To avoid revisiting the map later, these overlays should be in scope now:

- current unit location
- active route polyline
- destination marker
- arrival radius ring
- active alert pins
- previous alert pins
- recent detection pins
- account or repo address pins
- optional camera pins
- optional search zone or geofence polygons

These overlays need separate visibility rules and legend treatment.

## Icon And Marker Rules

Markers should communicate operational meaning immediately.

- destination marker: distinct target icon
- unit marker: current vehicle or agent icon
- active alert: critical red marker
- acknowledged alert: amber marker
- dismissed or historical alert: muted outline marker
- recent detection: cyan marker
- account address: neutral or branded marker

Clustering is required once density exceeds a readable threshold.

## Filtering Requirements

The map needs filtering that matches repo work, not general consumer maps.

At minimum:

- alert status
- time window
- plate text
- vehicle make
- vehicle model
- camera
- geofence zone
- case or account

Time window presets should include:

- last 24h
- last 7d
- last 30d
- all available

## Navigation Requirements

The navigation system must support true route generation, not just static line drawing.

Required capabilities:

- local geocoding
- route preview
- route recalculation
- ETA and distance summary
- route persistence in operator session
- recenter or follow mode
- end route
- resolve destination
- automatic arrival scan trigger using configured radius

Nice-to-have later but not required for first shipping pass:

- turn list drawer
- spoken guidance
- alternate route options

## Offline Requirement

The mapping stack must work without internet connectivity.

Recommended architecture:

- `MapLibre GL JS` for the map surface
- `PMTiles` for offline or local vector tile delivery
- `Valhalla` for self-hosted offline routing
- `Nominatim` for self-hosted geocoding

This stack is the cleanest fit for our current desktop web app and keeps the operator experience under our control instead of depending on external consumer map APIs.

## Backend Scope

Frontend-only changes will not be enough. The backend must own navigation state and local service integration.

Required backend additions:

- geocode endpoint
- route preview endpoint
- route activation endpoint
- route clear or resolve endpoint
- navigation session state on operator heartbeat or session record
- map layer preference persistence
- offline service health reporting

Recommended API additions:

- `GET /navigation/geocode`
- `POST /navigation/routes/preview`
- `POST /navigation/routes/activate`
- `POST /navigation/routes/clear`
- `GET /navigation/routes/active`
- `GET /navigation/map-layers`
- `PUT /navigation/map-layers`
- `GET /navigation/health`

## Contract Additions

The current operator session contract only records `navigation_active`. That is too thin for the final workflow.

Recommended operator session additions:

- `route_id`
- `destination_label`
- `destination_latitude`
- `destination_longitude`
- `follow_mode`
- `active_radius_feet`
- `auto_scan_armed`
- `visible_map_layers`
- `historical_alert_window`
- `idle_scan_enabled`

Recommended route response shape:

- route id
- destination label
- destination coordinates
- encoded geometry or coordinate path
- distance meters
- duration seconds
- route status
- created at and updated at

## Alert Persistence On Map

This is a hard requirement for the redesign:

- previous alerts must remain viewable while navigating
- previous alerts must remain viewable when no destination is active
- alert visibility must be independently toggleable from the route layer
- toggling alerts off must not disable navigation
- ending navigation must not clear historical alert layers

## Settings Scope

Map settings should remain, but only for defaults and lower-frequency preferences.

Keep in settings:

- default layer visibility
- default map style
- arrival auto-scan radius
- arrival auto-scan enabled default
- auto-center default
- clustering preference
- historical alert window default

Do not keep high-frequency controls only in settings:

- destination entry
- idle scan toggle
- alert layer visibility

## Acceptance Criteria

The redesign is complete only when all of the following are true:

1. The operator can set a destination from inside the map.
2. The operator can preview and start a route without leaving the map.
3. The operator can adjust arrival auto-scan radius from settings.
4. The operator can toggle idle scanning from the dashboard.
5. Previous alerts are visible both during navigation and when idle.
6. Alert layers can be toggled from the map toolbar or dock.
7. Alert layer defaults can be configured in settings.
8. The map works from offline tile and routing services.
9. Route and layer state survive refresh through the operator session.
10. The UI remains readable at laptop-height breakpoints.

## Build Order

To keep the work coherent, implementation should happen in this order:

1. Replace the map shell and move map controls into the map surface.
2. Add layer model and alert visibility controls.
3. Add destination modal and route preview workflow.
4. Add backend geocode and route contracts.
5. Switch from online tiles to local offline map services.
6. Persist route and map state through operator session and settings.

## Sources

The offline stack recommendation is based on official project documentation:

- MapLibre GL JS: https://maplibre.org/projects/gl-js/
- PMTiles and MapLibre integration: https://docs.protomaps.com/pmtiles/maplibre
- Valhalla API: https://valhalla.github.io/valhalla/api/
- Nominatim search API: https://nominatim.org/release-docs/latest/api/Search/
- Nominatim installation docs: https://nominatim.org/release-docs/4.5/admin/Installation/
