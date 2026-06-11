# DRIVER_MOBILE_UI_WIREFRAME_SPEC.md

## 1. Concise Product Design Summary

RepoScan Pro mobile should pivot from a desktop ops console to a single-driver field tool optimized for fast, low-light, in-vehicle use. The product should feel tactical and premium rather than consumer-social: near-black surfaces, restrained neon cyan emphasis, red reserved for hotlist and fault states, bold typography, large controls, and a calm layout that keeps the driver's attention on only the next useful action.

The core mobile workflow is:
- navigate to a target address from the dashboard
- monitor distance and entry into the configurable arrival radius
- if `Arrival Scan` is enabled, automatically enter `Arrival Active Scan Mode` when the vehicle reaches the address radius
- surface local detections only while inside that target radius
- surface hotlist alerts immediately anywhere, on any screen, regardless of navigation state or arrival-scan state
- make search and review usable in the field with fast filtering, grouped repeat sightings, and evidence-first detail views

Baseline mobile design assumptions:
- primary device: portrait phone layout, baseline artboard `390 x 844`
- supported width range: `360-430 px`
- safe-area aware top and bottom padding
- minimum tap target: `52 x 52 px`
- base spacing: `8 px` grid
- corner radius: `16-20 px`
- primary type scale: `32/24/18/16/14`
- monospace used for plates, GPS, timestamps, confidence, and camera/source values

Visual system:
- background: `#05090C`, `#0A1117`, `#101820`
- accent: `#38E8FF`
- accent glow: low-opacity cyan outer glow only on active states
- critical: `#FF4D5E`
- success: `#3DDC97` used sparingly for healthy system status and completed actions
- map and camera surfaces use low-glare overlays, desaturated imagery, and minimal chrome

Global interaction rules that must remain consistent across all screens:
- hotlist alerts are a system-level interrupt layer and always take priority
- arrival-based local scan can be enabled or disabled by the driver from the dashboard
- local vehicle and plate popups only appear inside the target address radius when arrival scan is enabled
- leaving the radius automatically ends arrival scan mode unless the user pins the session for review
- search by address returns every plate and vehicle detected at that address
- search by plate groups repeat sightings with expandable time/location history

## 2. Screen-by-Screen Wireframe Specification

### Screen 1. Main Dashboard Driver View

Purpose:
- primary driving screen with minimal distraction and immediate awareness of route, device health, and scan readiness

Entry state:
- app launch
- return point after dismissing local scan mode
- default screen after closing non-critical workflows

Wireframe:

```text
+--------------------------------------------------+
| STATUS BAR                                       |
| GPS OK | CAM LIVE | AI READY | SYNC 12P | PWR 82%|
+--------------------------------------------------+
| MAP / ROUTE                                      |
|                                                  |
|   current vehicle marker                         |
|   route line to target                           |
|   target pin + radius ring                       |
|   clustered detections / small pins              |
|                                                  |
|   floating state chip: EN ROUTE / IN RADIUS      |
+--------------------------------------------------+
| TARGET CARD                                      |
| 4128 W FULTON ST, CHICAGO IL                     |
| ETA 06 min | 0.8 mi | Status: En Route           |
| Radius: 300 ft | Arrival Scan: ON               |
| [Start / Resume Nav] [End Route]                 |
+--------------------------------------------------+
| QUICK ACTION DOCK                                |
| [Navigate] [Arrival Scan ON] [Hotlist]           |
| [History]  [Camera]          [Settings]          |
+--------------------------------------------------+
| BOTTOM SAFE AREA / NAVIGATION                    |
+--------------------------------------------------+
```

Layout specification:
- top status bar pinned, `48-56 px` high, icon + text pairs, always visible
- map occupies `50-58%` of viewport height in portrait
- target info card docks above quick actions and stays visible while navigating
- quick action dock is a `2 x 3` large-button grid in portrait so targets remain glove-friendly and one-thumb reachable
- map uses a dark, low-detail basemap with cyan route line, cyan radius outline, muted white destination pin, and red only for critical hotlist-related markers

Key content rules:
- target card shows full address, ETA, distance remaining, arrival state, and configured radius
- `Arrival Scan` toggle is visually binary and high contrast:
- `ON`: cyan outline + soft glow
- `OFF`: charcoal button with muted label
- map shows the arrival radius ring only when a navigation target exists
- current position remains visually stronger than other pins
- detection pins use clustering at zoomed-out levels to prevent noise

Behavior:
- entering the geofence around the active target changes `Arrival Status` from `En Route` to `Within Radius`
- if `Arrival Scan` is enabled, the app auto-transitions into `Arrival Active Scan Mode`
- if `Arrival Scan` is disabled, the target card updates to `Within Radius - Scan Off` and no local detection popups appear
- hotlist alerts interrupt this screen immediately with full-screen priority takeover
- if there is no active route, target card collapses into a compact `No active target` state and the radius ring is hidden

States to show in the wireframe set:
- idle / no target
- en route
- within radius with arrival scan off
- within radius with arrival scan on and automatic transition pending

### Screen 2. Arrival Active Scan Mode

Purpose:
- active on-scene capture and review mode used only when the driver is at the target radius and arrival scan is enabled

Entry state:
- automatic transition from dashboard upon entering target radius with arrival scan enabled
- optional manual re-entry while still inside radius

Wireframe:

```text
+--------------------------------------------------+
| HEADER                                           |
| ARRIVED AT TARGET                                |
| Scan Mode Active                                 |
| 4128 W FULTON ST, CHICAGO IL                     |
| [Exit Scan]                                      |
+--------------------------------------------------+
| LIVE CAMERA FEED                                 |
|                                                  |
|  [vehicle bounding box]                          |
|     Label: 2021 Toyota Camry                    |
|     Color: Black | Conf: 94% | Lane: Right      |
|  [plate bounding box]                            |
|     8ABC123                                      |
|                                                  |
| toast stack:                                     |
|  Local detection popup                           |
|  Plate + vehicle + confidence                    |
|                                                  |
+--------------------------------------------------+
| DETECTIONS PANEL (DRAGGABLE BOTTOM SHEET)        |
| Seen at this address                             |
| [thumb][plate][ymm][color][conf][time]           |
| [Capture][Tag][Note][Clear][Details]             |
| ------------------------------------------------ |
| [thumb][plate][ymm][color][conf][time]           |
| [Capture][Tag][Note][Clear][Details]             |
+--------------------------------------------------+
```

Layout specification:
- header fixed at top with high-contrast arrival state
- camera feed uses `45-60%` of the screen depending on bottom-sheet expansion
- detections panel is a resizable bottom sheet with three snap points:
- collapsed: shows latest `2` detections
- half: shows `4-5` detections
- full: turns into a full list with detail rows
- local popups appear as small stacked cards below the header and auto-dismiss into the detections panel

Overlay specification:
- vehicle boxes use cyan corner brackets
- plate boxes use brighter cyan with a monospace plate label
- hotlist match inside this screen does not stay a local toast; it immediately escalates to the hotlist takeover screen
- overlay labels show plate text, year/make/model, color, confidence, and direction/lane when available

Detection card specification:
- thumbnail left, text stack center, quick actions right or bottom depending on width
- metadata order:
- plate
- year make model
- color
- confidence
- timestamp
- GPS
- quick actions are large pills and remain visible without opening a context menu

Behavior:
- mode exists only inside the active address radius while arrival scan is enabled
- all detections shown in this panel are scoped to the current address session
- exiting the geofence automatically ends this mode and returns to the dashboard
- if the operator pins the session for review before leaving, the UI returns to a read-only review state instead of live scan
- dismissing a local popup does not remove it from the detections panel
- `Mark Clear` removes the card from the active live stack but keeps it in searchable history

States to show in the wireframe set:
- active live scan
- low confidence detection
- no current detections yet
- leaving radius / session ending

### Screen 3. Hotlist Alert Screen

Purpose:
- highest-priority system interrupt for any hotlist match, regardless of current route, screen, or arrival-scan setting

Entry state:
- any hotlist match event

Wireframe:

```text
+--------------------------------------------------+
| CRITICAL ALERT                                   |
| HOTLIST MATCH                                    |
| Audible + visual takeover                        |
+--------------------------------------------------+
| SNAPSHOT IMAGE                                   |
| [vehicle / plate frame]                          |
+--------------------------------------------------+
| PRIMARY RECORD                                   |
| Plate: 8ABC123                                   |
| 2021 Toyota Camry                                |
| Black | Conf 97%                                 |
| Direction: Northbound                            |
| Camera: Front LPR                                |
+--------------------------------------------------+
| LOCATION / TIME                                  |
| 33.74900, -84.38800                              |
| 4128 W FULTON ST, CHICAGO IL                     |
| 2026-03-27 22:14:08                              |
+--------------------------------------------------+
| ACTIONS                                          |
| [Navigate] [View Record]                         |
| [Mark Recovered] [Dismiss]                       |
| [Mute Audio This Event]                          |
+--------------------------------------------------+
```

Layout specification:
- full-screen takeover with red alert chrome and black background
- plate number is the largest text on screen
- snapshot sits above details to support immediate recognition
- action block is bottom-docked for thumb reach
- no secondary tabs or additional chrome during the alert

Priority styling:
- persistent red header pulse or edge glow until dismissed
- strong audio and vibration by default when enabled in settings
- background of the previous screen is fully obscured or heavily dimmed

Behavior:
- must appear immediately on top of every screen, including arrival scan mode, search, settings, and camera view
- cannot be missed by blending into existing UI; it is always a takeover state
- `Mute Audio This Event` silences only the current alert instance
- `Dismiss` closes the takeover but preserves the event in hotlist history
- `Navigate` opens routing to the current detection location or updates the active route if one exists
- `View Record` opens the detection detail record after the alert is acknowledged or dismissed

States to show in the wireframe set:
- critical active alert
- dismissed but retained in history
- muted current event

### Screen 4. Search and History Screen

Purpose:
- fast field retrieval of past scans by plate, address, vehicle details, time, and evidence state

Entry state:
- opened from dashboard quick action
- opened from hotlist takeover or detection detail back path

Wireframe:

```text
+--------------------------------------------------+
| SEARCH HEADER                                    |
| [ Plate ][ Address ][ Vehicle ][ Time ]          |
| Search input / date controls                     |
+--------------------------------------------------+
| FILTER CHIPS                                     |
| [Hotlist] [Current Shift] [Current Address]      |
| [Saved Evidence] [Low Conf] [High Conf]          |
+--------------------------------------------------+
| RESULTS LIST                                     |
| ------------------------------------------------ |
| [thumb] 8ABC123                                  |
| 2021 Toyota Camry | Black                        |
| 4128 W FULTON ST                                 |
| 33.74900, -84.38800                              |
| 2026-03-27 22:14 | 97% | HOTLIST                 |
| [Details] [Map] [Export] [Note] [Copy Plate]     |
| ------------------------------------------------ |
| [thumb] 8ABC123                                  |
| Seen 4 times                                     |
| Expand sightings timeline                        |
| ------------------------------------------------ |
+--------------------------------------------------+
```

Layout specification:
- top area combines segmented search mode and a single dominant query field
- filters live in a horizontally scrollable chip row below the search input
- results use evidence cards rather than dense tables
- list supports grouped and ungrouped modes:
- grouped by plate for repeat sightings
- grouped by address for address review
- sorted by most recent by default

Search mode behavior:
- `Plate`: supports full or partial entry and groups repeat detections into expandable sighting bundles
- `Address`: returns every plate and vehicle detected at that address, with total count and most recent activity at top
- `Vehicle`: searches by year, make, model, and color
- `Time`: filters by date range and optionally shift boundary

Result card rules:
- plate, vehicle, address, GPS, timestamp, and confidence are always visible without opening the card
- hotlist records get a red badge and float above non-hotlist results when sorted by relevance
- evidence-saved records get a subtle cyan or green evidence badge instead of using red
- copy and export actions are immediate and do not require opening detail first

Behavior:
- search should feel near-instant with progressive results and cached recent queries
- current address filter should prefill from the active route target when available
- repeated sightings expand inline to show times and locations
- opening a result pushes into the detection detail screen

States to show in the wireframe set:
- empty search
- active result list
- grouped repeat sightings
- address view with all detections at one address

### Screen 5. Detection Detail Screen

Purpose:
- evidence-first deep view for one detection record, including metadata, notes, and repeated sightings

Entry state:
- selected from search results
- selected from hotlist alert screen
- selected from arrival scan panel

Wireframe:

```text
+--------------------------------------------------+
| HEADER                                           |
| [Back] Detection Record                          |
+--------------------------------------------------+
| HERO IMAGE                                       |
| large frame capture                              |
+--------------------------------------------------+
| RECORD BLOCK                                     |
| 8ABC123                                          |
| 2021 Toyota Camry                                |
| Black | Conf 97%                                 |
| Camera: Front LPR                                |
| GPS: 33.74900, -84.38800                         |
| Address: 4128 W FULTON ST, CHICAGO IL            |
| Time: 2026-03-27 22:14:08                        |
+--------------------------------------------------+
| NOTES                                            |
| operator notes / evidence note preview           |
+--------------------------------------------------+
| EVENT TIMELINE                                   |
| Seen 22:14 here                                  |
| Seen 21:58 two blocks east                       |
| Seen 21:37 near prior address                    |
+--------------------------------------------------+
| ACTION BAR                                       |
| [Export] [Add Note] [Mark Important]             |
| [Attach to Address] [Open Map]                   |
+--------------------------------------------------+
```

Layout specification:
- hero image is top-heavy and immersive because this is an evidence review screen, not a driving screen
- plate number is anchored directly below the image in large monospace text
- metadata is shown as stacked read-only rows, not editable form fields
- notes and event timeline live in separate cards to preserve scanability

Behavior:
- if the record was seen multiple times, the event timeline is always visible and sorted newest first
- `Attach to Address` links the record into the relevant target-address case context
- `Open Map` launches a map detail view or native map intent
- if opened from hotlist, a small persistent hotlist badge remains visible in the header or record block

States to show in the wireframe set:
- single sighting
- multi-sighting timeline
- hotlist-tagged record

### Screen 6. Camera View Screen

Purpose:
- dedicated live camera monitoring view for manual feed review while parked or staged

Entry state:
- opened from dashboard quick action
- opened from arrival scan workflow for manual review

Wireframe:

```text
+--------------------------------------------------+
| HEADER                                           |
| Camera View                                      |
| [Front] [Left] [Right] [Rear] [Split]            |
+--------------------------------------------------+
| LIVE FEED                                        |
| [single or dual feed]                            |
| AI boxes / labels when enabled                   |
| recording badge                                  |
+--------------------------------------------------+
| CAMERA CONTROLS                                  |
| [Night] [IR] [Exposure] [Zoom] [Focus]           |
| [AI Overlay ON] [Capture Frame]                  |
+--------------------------------------------------+
| STATUS STRIP                                     |
| REC | 1080p | 30 fps | Front LPR                 |
+--------------------------------------------------+
```

Layout specification:
- camera feed dominates the screen
- source selector is a segmented control directly under the header
- controls use oversized icon+label buttons and a bottom-docked layout
- split mode uses two stacked feeds in portrait

Behavior:
- intended for parked or low-speed manual review, not the default driving screen
- AI overlay toggle hides or shows all detection boxes and labels
- capture action stores a still frame and optionally creates a reviewable detection artifact
- recording state remains visually persistent
- hotlist alerts still interrupt this screen immediately

States to show in the wireframe set:
- single camera
- split camera
- overlay on
- overlay off

### Screen 7. Settings Screen

Purpose:
- mobile control surface for scanning logic, alert behavior, camera tuning, storage, sync, and map/navigation defaults

Entry state:
- opened from dashboard quick action

Wireframe:

```text
+--------------------------------------------------+
| HEADER                                           |
| Settings                                         |
+--------------------------------------------------+
| SCANNING                                         |
| Auto-enable arrival scan             [ON/OFF]    |
| Arrival scan feature global          [ON/OFF]    |
| Radius size                             [slider] |
| Duplicate suppression                   [slider] |
| Minimum confidence                      [slider] |
+--------------------------------------------------+
| ALERTS                                           |
| Hotlist alerts                       [ON/OFF]    |
| Sound                                [ON/OFF]    |
| Vibration                            [ON/OFF]    |
| Alert volume                          [slider]   |
| Alert persistence                     [list]     |
+--------------------------------------------------+
| CAMERA                                           |
| Night mode                          [ON/OFF]     |
| IR control                          [ON/OFF]     |
| Exposure lock                       [ON/OFF]     |
| Resolution                          [list]       |
| Stream quality                      [list]       |
| Overlay labels                      [ON/OFF]     |
+--------------------------------------------------+
| STORAGE AND SYNC                                 |
| Local storage used                 18.2 GB       |
| Sync status                        Pending 12    |
| Upload pending                     00:14 ETA     |
| Export path                        /evidence/... |
| Auto-delete temp captures          [ON/OFF]      |
+--------------------------------------------------+
| MAP AND NAVIGATION                                |
| Default map mode                    [list]       |
| Auto-center on vehicle              [ON/OFF]     |
| Show radius ring                    [ON/OFF]     |
| External or internal nav            [list]       |
+--------------------------------------------------+
```

Layout specification:
- settings are organized into stacked section cards with sticky section labels or quick-jump anchors
- toggles, sliders, and select rows use a consistent right-aligned control pattern
- destructive or risky settings are separated visually and use red copy only when necessary

Behavior:
- `Arrival Scan feature global` disables arrival-scan behavior everywhere, even if a target is active
- `Auto-enable arrival scan on entering address radius` controls whether scan mode starts automatically or requires manual confirmation at arrival
- hotlist alerts should default to enabled and visually warn before allowing them to be turned off
- changes should be immediately reflected in the dashboard state chips and labels

States to show in the wireframe set:
- normal settings list
- warning state for disabled hotlist alerts
- storage nearly full

## 3. Suggested Component Hierarchy for Each Screen

### Dashboard Driver View

- `MobileAppShell`
- `SystemStatusBar`
- `DriveMapCard`
- `MapOverlayChips`
- `TargetInfoCard`
- `QuickActionDock`
- `BottomNav`
- `GlobalHotlistInterruptLayer`

### Arrival Active Scan Mode

- `MobileAppShell`
- `ArrivalScanHeader`
- `ScanStateChipRow`
- `LiveCameraSurface`
- `DetectionOverlayLayer`
- `LocalDetectionToastStack`
- `AddressDetectionsBottomSheet`
- `DetectionActionTray`
- `GlobalHotlistInterruptLayer`

### Hotlist Alert Screen

- `HotlistAlertTakeover`
- `CriticalAlertHeader`
- `AlertSnapshotCard`
- `HotlistPrimaryRecord`
- `HotlistLocationTimeCard`
- `HotlistActionDock`

### Search and History Screen

- `MobileAppShell`
- `SearchModeSegmentedControl`
- `SearchQueryBar`
- `FilterChipRail`
- `SearchResultsList`
- `DetectionResultCard`
- `GroupedSightingAccordion`
- `BottomNav`
- `GlobalHotlistInterruptLayer`

### Detection Detail Screen

- `MobileAppShell`
- `DetailHeader`
- `DetectionHeroImage`
- `DetectionIdentityCard`
- `DetectionMetadataList`
- `DetectionNotesCard`
- `SightingTimelineCard`
- `DetailActionDock`
- `GlobalHotlistInterruptLayer`

### Camera View Screen

- `MobileAppShell`
- `CameraViewHeader`
- `CameraSourceSegmentedControl`
- `CameraFeedSurface`
- `CameraOverlayLayer`
- `RecordingStatusBadge`
- `CameraControlDock`
- `BottomNav`
- `GlobalHotlistInterruptLayer`

### Settings Screen

- `MobileAppShell`
- `SettingsHeader`
- `SettingsSectionCard`
- `ToggleRow`
- `SliderRow`
- `SelectRow`
- `StorageStatusCard`
- `BottomNav`
- `GlobalHotlistInterruptLayer`

## 4. Suggested Mobile Navigation Structure

Primary navigation:
- bottom navigation with `Drive`, `Search`, `Camera`, and `Settings`
- `Drive` is the default landing screen and contains dashboard, target card, and quick actions
- `Search` owns history and evidence retrieval rather than splitting history into a separate primary tab
- `Camera` is a manual monitoring tool, not the default operational state
- `Settings` remains fourth and lowest-frequency

Contextual navigation:
- `Arrival Active Scan Mode` is not a permanent bottom-nav destination
- it is a contextual route entered automatically from `Drive` when the user reaches the address radius and arrival scan is enabled
- it exits back to `Drive` when the session ends or the user taps `Exit Scan`

Global interrupt layer:
- `Hotlist Alert Screen` is outside the normal navigation stack
- it sits in a root-level modal or takeover layer above every route
- it can deep-link into `Detection Detail` or update the current route target after dismissal

Secondary access:
- `History` is surfaced as the default content mode inside `Search`
- `Hotlist` is surfaced as a quick action from `Drive` and as a filter or inbox within `Search`, but hotlist events themselves should never rely on the user manually opening that screen

Recommended route map:
- `/drive`
- `/scan/arrival`
- `/search`
- `/search/address/:addressId`
- `/search/plate/:plateText`
- `/detection/:detectionId`
- `/camera`
- `/settings`

## 5. UX Notes for Field Safety and Usability

- Keep the driving dashboard glanceable. The driver should understand route state, arrival state, and system health in under two seconds.
- Use one-thumb reach for the primary action zone. Critical actions belong in the lower third of the screen, not the top corners.
- Avoid requiring text entry while driving. Recent addresses, recent plates, and quick filters should be selectable from chips and presets.
- Use red only for critical alerts, dangerous settings, and severe faults. Overusing red will weaken hotlist urgency.
- Use cyan for active but non-critical state changes such as route live, scan armed, overlay enabled, and selected controls.
- Use soft glow sparingly. The UI should feel premium at night, not blurry or game-like.
- Monospace values improve scan speed for plates, coordinates, confidence values, and times.
- Support dim, low-glare night usage. Avoid bright white panels and large untreated maps.
- Local address popups should be visually noticeable but still secondary to road awareness. They should collapse into the detections panel instead of blocking the full screen.
- Hotlist alerts must be impossible to miss and should use multimodal signaling: color, motion, audio, and haptics where available.
- Search results should favor evidence cards over dense tables so the user can identify the right record quickly in poor lighting or high-stress conditions.
- Manual camera review should clearly indicate that it is best used while parked or staged.

## 6. Optional Implementation Notes

- In React, model the app shell around a root route with a global hotlist interrupt provider mounted above page routes.
- In Tailwind, define the tactical theme with semantic tokens such as `bg-shell`, `bg-surface`, `text-primary`, `text-muted`, `accent-cyan`, and `critical-red` instead of hardcoding colors in components.
- In shadcn, use dialog or drawer primitives for the hotlist takeover and the arrival detections bottom sheet, then harden the visual styling away from consumer defaults.
- In Capacitor or Android, route hotlist events through native notification, vibration, and audio channels so alerts remain reliable even when app state changes.
- Keep map, camera, and alert layers modular. The dashboard, arrival scan screen, and detail screens all need to reuse detection cards, status chips, and evidence metadata rows.
- Treat `Arrival Scan` state, `Within Radius` state, and `Hotlist Alert` state as independent UI signals. The interface should never let local-scan suppression hide hotlist behavior.
