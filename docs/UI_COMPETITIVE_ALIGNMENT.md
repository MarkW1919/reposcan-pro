# UI Competitive Alignment — Vigilant, DRN, Car Detector

## Purpose

Align the RepoScan Pro desktop and mobile interfaces with the UI patterns that repossession industry operators already know from Vigilant Solutions (Motorola), DRN (Digital Recognition Network), and Clearplan. Repo agents switching to RepoScan Pro should feel immediate familiarity with detection feeds, alert styling, hit confirmation flows, and search patterns.

## Competitor UI Summary

### Vigilant Solutions / CarDetector Mobile (Motorola)

**In-car (CarDetector Mobile):**
- Four simultaneous panels: active camera feed, detection viewer, hit list, scrolling plate list
- Auto-scrolling plate list pauses on tap, resumes on deselect
- Hit view shows IR plate crop + color overview side by side
- Alarm priority color coding: Red (High), Orange (Medium), Yellow (Low)
- Day/night mode toggle
- Large touch targets, distraction-free layout
- Audio + visual alerts, sub-second latency

**Desktop (VehicleManager 8.0):**
- Left sidebar navigation (Vehicle Search, Hot Lists, Dashboard, System Management)
- Dashboard: system status tiles (camera health) + up to 6 configurable data tiles (drag-and-drop, resizable)
- Detection results: scrollable list + map view + filmstrip (horizontal thumbnail row of top 10 vehicles)
- Detection record: IR plate crop, color overview, OCR, GPS, timestamp, camera ID, vehicle make/model/color
- Alert page: filter tiles with color assignments, alert list, hit detail panel, map
- Dark/light mode toggle
- AI-powered "Assist" natural language search

**Mobile (Vigilant Mobile Companion):**
- Bottom scan ribbon (current session plates)
- Pinch-to-zoom, swipe navigation
- Real-time hotlist popup notifications
- GPS-tagged scans with map pins

### DRN / DRNsights

**Desktop (DRNsights):**
- Vehicle search by VIN, plate, reference ID with make/model/year filters
- Results table with "Map It" to plot all sighting locations
- 4-digit frequency score per location: sightings in [0-30d][31-90d][91-180d][180+d], each digit 0-9
- Timeline visualization showing sighting patterns
- Address analysis with zone drawing (circles, rectangles, freeform polygons)
- Auto-tagging: workplace (daytime scans) vs residential (evening/night)
- PDF export with map pins and addresses

**Field (Clearplan):**
- Map/satellite hybrid with real-time agent tracking
- DRN feed: all LPR alerts in one place
- Single-button validate/reject per scan
- Traffic-light status: Green (proceed), Yellow (hold), Red (cancel)
- Google Maps integration with nav
- Auto-removal of recovered/closed accounts

### Car Detector / Up4Repo (Low-Cost Mobile)

- Phone-mounted scanning (up to 30 mph)
- Immediate hotlist match notification
- Multi-image auto-capture, auto-email to account owner
- Voice note recording
- Up to 250K hotlist entries
- Minimal analytics — lean field scanning tool

## What RepoScan Pro Already Matches

| Pattern | Notes |
|---|---|
| Dark tactical theme (cyan accent, red critical) | Stronger than Vigilant's corporate blue |
| Hotlist full-screen takeover alert | Matches Vigilant/DRN priority interrupt |
| Audio + vibration + visual alert signaling | Spec'd and implemented |
| Red reserved for critical, cyan for active states | Matches alarm priority philosophy |
| Evidence-first detection detail | Mobile wireframe and desktop overlay |
| Search by plate/address/vehicle/time | Implemented |
| Map with route, radius ring, clustered pins | Implemented (Leaflet, dark basemap) |
| Arrival scan geofence | Unique advantage over Vigilant/DRN |
| Recovery account intake (plate, VIN, address) | Implemented |
| Operator sessions + role-based UI | Implemented |
| Day/night mode | In settings |
| Monospace for plates, GPS, timestamps, confidence | In spec and CSS |
| Configurable layout presets | 6 presets — more flexible than Vigilant |

## Gaps to Close

### P0 — Field Credibility (agents will notice immediately)

#### 1. Dual-Image Detection Hero

**Industry pattern:** Every professional system (Vigilant, DRN) shows two images per detection: an IR plate crop for OCR verification and a color overview of the vehicle for visual confirmation. Both are displayed side by side in detection detail and alert views.

**Current state:** Detection detail overlay fetches frame and plate crop via `fetchDetectionFrameObjectUrl` and `fetchDetectionPlateCropObjectUrl`, but the layout does not present them as a prominent side-by-side dual-image hero.

**Change:** In both the detection detail overlay and the hotlist alert takeover, render the plate crop on the left (40% width) and the color overview on the right (60% width) as the first content block below the header. Use a dark card background with 1px cyan border. If only one image is available, show it full width.

#### 2. Auto-Scrolling Detection Feed

**Industry pattern:** CarDetector Mobile's scrolling plate list is the core interaction. Plates scroll in continuously as they're read. Clicking a row pauses the scroll so the agent can review. Clicking away or pressing a resume button restarts the scroll. This is the single most expected interaction for anyone who has used Vigilant or DRN in-car software.

**Current state:** The Plate Detection Table is a static table that requires manual review.

**Change:** Replace the static table with a live auto-scrolling feed component. New detections push to the top and the list scrolls automatically. Clicking a row pauses the auto-scroll and highlights the selected detection. Clicking away or pressing a "Resume" button restarts the scroll. Show a subtle "PAUSED" indicator when auto-scroll is stopped.

#### 3. Severity Color Bands on Alert/Detection Rows

**Industry pattern:** CarDetector Mobile uses Red/Orange/Yellow left-edge color bands on hit rows to indicate alarm priority. This is instant visual triage.

**Current state:** Alerts carry severity data (`critical`, `priority`, `watch`) but rows use uniform styling.

**Change:** Add a `4px` left border to each alert and hotlist-matched detection row:
- `critical` → `var(--critical)` (#ff4d5e)
- `priority` → `var(--warn)` (#ffb347)
- `watch` → `#f5d742` (yellow)

The border should be the leftmost visual element in the row, before any thumbnail or text.

### P1 — Intelligence Parity (what differentiates a serious tool)

#### 4. Sighting Frequency Score

**Industry pattern:** DRN's 4-digit frequency score (e.g., `3210` = 3 sightings in last 30 days, 2 in 31-90, 1 in 91-180, 0 in 180+) is the industry standard for communicating location intelligence. Repo agents are trained to read this. A high first digit means "go now."

**Current state:** No sighting frequency scoring. Search returns flat results without location clustering or recency weighting.

**Change:** Compute a 4-digit frequency score per plate-location cluster (detections within ~150m grouped together). Display the score as a monospace badge on search result cards and on the detection detail screen. Color the first digit cyan when >= 3, indicating recent high activity.

#### 5. Traffic-Light Dispatch Status

**Industry pattern:** Clearplan uses Green/Yellow/Red to signal whether a field agent should proceed, hold, or cancel a recovery. This is a safety-critical workflow signal.

**Current state:** Dispatch assignments have status fields but use plain text labels.

**Change:** Render dispatch assignment status as colored pill badges:
- `assigned` / `en_route` / `on_scene` → Green pill, white text
- `hold` / `pending_review` → Yellow pill, dark text
- `cancelled` / `abort` → Red pill, white text

Use these pills in the dispatch board panel, the alert detail overlay, and the recovery accounts screen.

#### 6. Hit Confirmation Buttons (Correct / Incorrect)

**Industry pattern:** Vigilant CarDetector shows "Correct" and "Incorrect" buttons on every hotlist hit view. This feeds OCR accuracy tracking and prevents false-positive recoveries.

**Current state:** Hotlist alert has Acknowledge/Dismiss actions but no explicit correct/incorrect verification.

**Change:** Add "Confirm Match" (green) and "False Positive" (red) buttons to the hotlist alert takeover, positioned above the existing Acknowledge/Dismiss actions. These should write to the review workflow (maps to the existing `createReview` API with `action: "confirm"` or `action: "false_positive"`).

### P2 — Analytical Depth

#### 7. Sighting Timeline Component

**Industry pattern:** DRNsights and VehicleManager both show temporal timelines of when a plate was seen over days/weeks, revealing patterns (daily routines, work/home locations).

**Change:** Add a horizontal timeline bar to the detection detail screen and to grouped search results. Each mark represents a sighting, positioned along a time axis. Color-code marks by location cluster.

#### 8. Filmstrip Thumbnail Row

**Industry pattern:** Vigilant shows the top 10 matched vehicles in a horizontal filmstrip above search results for rapid visual identification.

**Change:** Add a horizontally scrollable thumbnail strip above the search results list. Each thumbnail shows the plate crop and plate text. Clicking scrolls the results list to that detection.

#### 9. Camera Health Summary Tile

**Industry pattern:** VehicleManager 8.0 shows non-configurable system status tiles on the dashboard displaying camera count and health by type.

**Change:** Add a compact camera health summary to the dashboard status bar or as a rail panel: "4 cameras — 3 online, 1 offline" with colored dots (green/red). This already exists in the status footer but should be more prominent and show per-camera health.

#### 10. Map Zone Drawing

**Industry pattern:** Both DRNsights and VehicleManager let users draw circles, rectangles, and freeform polygons on the map to define geographic search areas.

**Change:** Add Leaflet Draw plugin support for circle and polygon drawing. Drawn zones should filter the detection feed and search results to only show detections within the drawn area.

### P3 — Advanced Intelligence

#### 11. Workplace / Residential Auto-Tagging

**Industry pattern:** DRN auto-classifies sighting locations as "workplace" (daytime scans, 6am-6pm) or "residential" (evening/night scans, 6pm-6am) based on temporal patterns.

**Change:** When displaying location clusters in search results or on the map, tag locations with "Likely Workplace" or "Likely Residential" based on the time distribution of scans at that location.

#### 12. PDF Export from Search

**Industry pattern:** DRNsights exports search results as PDF documents including a map with all result pins and full detection details.

**Change:** Add an "Export PDF" action to the search results toolbar. The export should include a map snapshot with pins, a summary table of results, and the sighting frequency score for each location.

#### 13. Location Alert Subscriptions

**Industry pattern:** DRN offers automated email/push notifications when a plate is subsequently scanned (Live Alert subscriptions).

**Change:** Add a "Watch this plate" action to the detection detail screen. When a watched plate is re-detected, surface it as a priority notification even if it is not on the hotlist.

## Visual Reference: Detection Card Layout (Target)

```
+------+------------------------------------------+----------+
| PLATE|  8ABC123              97%  HOTLIST        |          |
| CROP |  2021 Toyota Camry · Black                | [Verify] |
| IMG  |  4128 W Fulton St, Chicago IL             | [Map]    |
|      |  37.42172, -122.08408 · 22:14:08          | [Note]   |
|      |  Front LPR · Score: 3210                  | [Export] |
+------+------------------------------------------+----------+
```

- Plate crop image: left column, 80x80 or larger
- Plate text: largest text, monospace, bold
- Confidence + hotlist badge: inline right of plate
- Vehicle YMM + color: second line
- Address: third line
- GPS + timestamp: fourth line, monospace, muted
- Camera + frequency score: fifth line
- Quick actions: right column, stacked icon buttons

## Visual Reference: Alert Row Severity Styling (Target)

```
┌──┬────────────────────────────────────────────┐
│▌▌│  8ABC123  White Toyota Camry   97%  CRIT   │  ← 4px red left border
│▌▌│  Shoreline Blvd · 01:14:22 · Tow Ready     │
└──┴────────────────────────────────────────────┘
┌──┬────────────────────────────────────────────┐
│▌▌│  3LPM771  Black Ford Explorer  89%  PRI    │  ← 4px orange left border
│▌▌│  Rengstorff Ave · 01:12:08 · Departure Risk│
└──┴────────────────────────────────────────────┘
┌──┬────────────────────────────────────────────┐
│▌▌│  1JFD552  Blue Chevy Tahoe     82%  WATCH  │  ← 4px yellow left border
│▌▌│  Elm side street · 01:04:57 · Assignment    │
└──┴────────────────────────────────────────────┘
```

## Implementation Order

1. Severity color bands (CSS-only, immediate visual impact)
2. Dual-image detection hero (layout change in detail overlay + alert)
3. Auto-scrolling detection feed (component rewrite)
4. Confirm Match / False Positive buttons on hotlist alert
5. Traffic-light dispatch pills
6. Sighting frequency score computation + display
7. Sighting timeline component
8. Filmstrip thumbnail row
9. Camera health tile
10. Map zone drawing (Leaflet Draw plugin)
11. Workplace/residential tagging
12. PDF export
13. Location alert subscriptions
