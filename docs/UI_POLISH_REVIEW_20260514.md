# UI polish review — 2026-05-14

Structured review of the current `apps/ui` after Codex's dashboard refactor
(`507795f` plus follow-ups), benchmarked against:

- [docs/UI_PRO_GRADE_STRATEGY.md](UI_PRO_GRADE_STRATEGY.md) (acceptance bar)
- [docs/UI_COMPETITIVE_ALIGNMENT.md](UI_COMPETITIVE_ALIGNMENT.md) (Vigilant / DRN / Clearplan baseline)
- [docs/ui-operations-admin-implementation-spec.md](ui-operations-admin-implementation-spec.md) (target IA)
- [docs/UI_WORKFLOWS.md](UI_WORKFLOWS.md) (mission workflows)

## TL;DR

The product is **closer to professional-grade than it looks at first glance** —
the dual-image evidence hero, auto-scrolling detection feed, and left-edge
severity bands (all P0 items in the competitive doc) are already implemented
on the older `console` path. The new dashboard refactor delivers a flexible
widget shell and an Operations / Admin split that matches the spec, but the
new dashboard widgets do **not yet inherit the field-tested severity
language** from the console feed, leaving the highest-frequency screen
visually softer than the screen it replaces.

The fastest path to "exceed professional bar" is to harmonize the dashboard
widgets with the same priority-language and information density already
proven in the console feed, fix three concrete visual-consistency bugs, and
land the still-missing P1 intelligence items (frequency score, dispatch
traffic-light, confirm/false-positive on hit alerts).

## What is already at or above the bar

| Capability | Spec | Status | Where |
|---|---|---|---|
| Operations / Admin shell split | ops-admin-spec | ✅ Implemented | App.tsx ~line 5050 onward, `currentShell` derivation |
| Bottom Uconnect-style toolbar | dashboard-refactor | ✅ Implemented | [UconnectStyleToolbar.tsx](../apps/ui/src/components/dashboard/UconnectStyleToolbar.tsx) |
| Instrument-cluster status bar | dashboard-refactor | ✅ Implemented | [InstrumentStatusBar.tsx](../apps/ui/src/components/dashboard/InstrumentStatusBar.tsx) |
| Configurable widget layout (5 modes) | dashboard-refactor | ✅ Implemented | [dashboard-config.ts](../apps/ui/src/dashboard-config.ts) |
| LocalStorage persistence + schema versioning | implicit | ✅ `reprovision.dashboard.config.v1` |
| Drag-to-reorder + keyboard fallback | accessibility | ✅ Pointer drag + Up/Down buttons | [DashboardCustomizePanel.tsx](../apps/ui/src/components/dashboard/DashboardCustomizePanel.tsx) |
| Dual-image detection hero (plate crop + frame) | competitive P0 #1 | ✅ Implemented | [DetectionEvidenceHero.tsx](../apps/ui/src/components/detections/DetectionEvidenceHero.tsx) |
| Auto-scrolling detection feed with hover/manual pause | competitive P0 #2 | ✅ Implemented | [DetectionFeed.tsx](../apps/ui/src/components/console/DetectionFeed.tsx) |
| Left-edge severity color bands | competitive P0 #3 | ✅ On `DetectionFeedRow` only | [DetectionFeedRow.tsx](../apps/ui/src/components/console/DetectionFeedRow.tsx) + styles.css:3100-3137 |
| Touch-target ≥44 px | accessibility | ✅ Multiple selectors enforce | styles.css min-height: 44px in 4 places |
| Reduced-motion preference | accessibility | ✅ `@media (prefers-reduced-motion: reduce)` | styles.css:7220 |
| Map navigation HUD (route, distance, ETA, controls) | pro-grade roadmap | ✅ Implemented | `MapStagePanel` in App.tsx:2437 |
| Hotlist alert takeover with verification gate | pro-grade roadmap | ✅ Implemented | App.tsx, references DetectionEvidenceHero |

## Concrete gaps and polish items

Ranked by impact-per-effort. P0 is "field credibility" — agents notice
immediately. P1 is "intelligence parity" — separates a serious tool from a
demo. P2 is "polish" — distinguishes professional from acceptable. P3 is
"future."

### P0 — Field credibility (do first)

#### 1. Dashboard widgets don't inherit severity bands

**Observation**: [CompactDetectionCard.tsx](../apps/ui/src/components/dashboard/CompactDetectionCard.tsx)
and [RecentDetectionHistoryCard.tsx](../apps/ui/src/components/dashboard/RecentDetectionHistoryCard.tsx)
use `StatusPill` for severity but no left-edge color band. The older
[DetectionFeedRow.tsx](../apps/ui/src/components/console/DetectionFeedRow.tsx)
does. When an operator switches from the legacy console to the new
dashboard, the priority signal collapses from a high-contrast 4 px band to
a small pill on the right side of the card. That is a real regression in
glance-readability — the exact opposite of "exceed the professional bar."

**Fix**: Add `severity-band severity-band--<severity>` classes to both
dashboard card wrappers. Reuse the existing CSS rules at styles.css:3100-3137
— no new color tokens needed. ~30 lines of changes total.

#### 2. Two different "critical reds" in CSS

**Observation**: `dashboard.css` defines `--critical: #ff6a6a` while
`styles.css` uses `#ff4d5e` (per the competitive doc spec). The two reds
read differently next to each other. When the instrument-status-bar segment
glows one red and a severity band next to it glows the other, the inconsistency
shows.

**Fix**: Move all design tokens (color, type scale, spacing, shadow,
border-radius) into a single `apps/ui/src/tokens.css` imported by both
files. Pick one critical red (recommend the original `#ff4d5e` — it is
documented and consistent with the IACP / CarDetector reference). Same
audit for `--cyan`, `--warn`, `--success`, `--muted`.

#### 3. Drag handle is `:::` text, not a glyph

**Observation**: [DashboardCustomizePanel.tsx](../apps/ui/src/components/dashboard/DashboardCustomizePanel.tsx:204)
literally renders the three-colon string. Looks unfinished.

**Fix**: Replace with a real drag-grip glyph (Unicode `⋮⋮` doubled or a
tiny inline SVG of six dots). Keep the `aria-label="Drag to reorder X"`
that is already in place.

#### 4. Customize panel doesn't close on Escape

**Observation**: The scrim click closes the panel, but pressing Escape
does nothing. Operators in the cab will reach for Esc before they reach for
the small "Done" button.

**Fix**: Add a `useEffect` that listens for `keydown` Escape on
`document` while the modal is open. Same pattern is already used for
`destination-modal` per App.tsx:2826.

#### 5. Instrument-status-bar brand mark is generic ("RS")

**Observation**: [InstrumentStatusBar.tsx:39](../apps/ui/src/components/dashboard/InstrumentStatusBar.tsx#L39)
shows a square with "RS" text. Looks like an unfinished placeholder.

**Fix**: Either (a) replace with the actual RepoScan Pro mark / SVG logo,
or (b) drop the square entirely and let the eyebrow + brand label carry the
identity (cleaner for a recovery console — less decoration). Recommend (b)
because [UI_PRO_GRADE_STRATEGY.md](UI_PRO_GRADE_STRATEGY.md) explicitly
calls out "avoid marketing-style cards, oversized decoration."

### P1 — Intelligence parity (do next)

Items 4-6 from [UI_COMPETITIVE_ALIGNMENT.md](UI_COMPETITIVE_ALIGNMENT.md)
that haven't landed yet:

#### 6. Sighting frequency score (DRN-style 4-digit badge)

**Observation**: Not implemented. No code matches `frequency`,
`frequencyScore`, or the 4-digit pattern. Agents trained on DRN will
expect this on every detection card.

**Fix**: Compute a per-(plate, ~150m location cluster) score `NNNN` where
each digit is the count of sightings in [0-30d, 31-90d, 91-180d, 180+d]
buckets, capped at 9. Display as a monospace badge:
`SCORE 3 2 1 0` with the first digit cyan when ≥3. Wire into
search result rows, detection detail, and (compact) dashboard cards.

#### 7. Traffic-light dispatch status pills

**Observation**: First-deployment scope per
[UI_PRO_GRADE_STRATEGY.md](UI_PRO_GRADE_STRATEGY.md#first-deployment-scope)
explicitly removes dispatcher / unit-assignment surfaces. But the
single-operator recovery-state model (`active / acknowledged / dismissed /
recovered / false_positive`) still benefits from a colored pill rather than
plain text. We have the data; the visual hasn't landed.

**Fix**: Add a `RecoveryStatePill` component (or extend `StatusPill` with a
recovery-state preset) that maps states to the colors agreed in the
pro-grade strategy: green for `recovered`, cyan for `acknowledged`, amber
for `active`, gray for `dismissed`, red for `false_positive`.

#### 8. Confirm Match / False Positive on hit alert

**Observation**: The hotlist alert takeover already references
`DetectionEvidenceHero`, but I did not find explicit "Confirm Match"
(green) and "False Positive" (red) buttons. The competitive doc calls
this out as the single most-expected hit interaction.

**Fix**: Add the two buttons above the existing Acknowledge / Dismiss row
in the alert takeover. Wire to the existing `createReview` API with
`action: "confirm"` or `action: "false_positive"`. Keyboard
shortcuts: `C` and `F` (the pro-grade doc roadmap calls out the keyboard
shortcuts pattern explicitly).

#### 9. Visible auto-scroll PAUSED state in dashboard view

**Observation**: The console-screen feed has a clear "Auto-scroll
paused / Resume" toolbar. The dashboard's live-detections widget
([CompactDetectionCard.tsx](../apps/ui/src/components/dashboard/CompactDetectionCard.tsx))
is a card list, not the auto-scrolling feed. Either the dashboard widget
should host the same `DetectionFeed` (recommended — reuse the proven
auto-scroll behavior) or it should at least signal that the dashboard view
is a snapshot, not a live feed.

**Fix**: Replace the static `CompactDetectionCard` list in the dashboard's
`liveDetections` widget with a height-constrained `DetectionFeed`
instance. The dashboard widget frame already supplies the title and
status pill; the feed renders inside its body.

### P2 — Polish (do third)

#### 10. App.tsx is 9,179 lines

**Observation**: One file holds the AppScreen / AppShell / SearchMode /
SettingsSection state machines, the OpsMap, MapStagePanel,
DestinationModal, ConsoleScreen, and the entire `App` function with its
huge JSX tree. Future polish work and component reuse are constrained
by the size.

**Fix**: Extract in increments — start by moving each top-level screen
(`ConsoleScreen`, `SearchScreen`, `AccountsScreen`, `HotlistsScreen`,
`SettingsScreen`) into a sibling file under `apps/ui/src/screens/`.
Keep `App.tsx` as the routing + state shell. Don't try to fix
everything at once — `MapStagePanel` and `DestinationModal` can stay
inline for the first pass.

#### 11. styles.css is 7,227 lines, dashboard.css is 1,032 lines

**Observation**: Same problem at the CSS layer. Worse: the two files
duplicate some tokens (the critical-red mismatch above is a symptom).

**Fix**: Establish the file split now even before extracting:
- `tokens.css` — design tokens only (colors, type scale, spacing, shadow,
  radius, transitions)
- `base.css` — resets, body, typography, form controls
- `dashboard.css` — dashboard shell + widgets (existing)
- `console.css` — legacy console-screen-specific
- `map.css` — map stage, leaflet customizations
- `evidence.css` — detail overlay, hotlist takeover, evidence hero

#### 12. Customize panel reorder doesn't visually preview the dashboard

**Observation**: Drag a widget up or down — the customize panel reorders
internally, but the user has to close the panel and look at the dashboard
to see whether the new order makes sense. Behind-the-scenes: the change
DOES save and the dashboard re-renders, but the customize panel itself
covers most of the screen.

**Fix**: Reduce the customize panel width to 40 % so the dashboard remains
visible on the left and the reorder is immediate. Use the existing scrim
(transparent) only for click-to-dismiss, not full-opacity overlay.

#### 13. No layout-mode keyboard shortcut

**Observation**: Switching between `default / driving / scanning / review
/ minimal` requires opening the customize panel and clicking a mode
button. A repo agent who drives all day will want a one-keypress switch.

**Fix**: Add a global keyboard handler in `App.tsx` for `Ctrl+1..5`
mapping to the five modes. Surface the binding as a tiny hint in the
customize panel modes section.

#### 14. The dashboard's compact-detection-card uses `|` (pipes) as separators in metadata

**Observation**: [CompactDetectionCard.tsx:30](../apps/ui/src/components/dashboard/CompactDetectionCard.tsx#L30)
joins color, distance, and confidence with `"  |  "`. That works but
looks like web 1.0. The competitive doc's reference card uses bullet
separators (`·`).

**Fix**: Switch the separator to `·` with consistent spacing, OR drop the
separators entirely and use spaced inline `<span>` with `gap` on the
parent flex.

#### 15. Status pill text size is 0.68 rem with letter-spacing 0.08em

**Observation**: dashboard.css:352-359. At 0.68 rem on a typical
16 px base, that is ~11 px text. For an in-cab display under field
conditions, this is too small. The pro-grade doc calls for "large
typography" in operator shift mode.

**Fix**: Raise base status-pill text to 0.78 rem and let the shift-mode
preset scale it to 0.92 rem via a CSS variable. Same applies to
`.dashboard-widget__eyebrow` at 0.68 rem.

### P3 — Future (do later, after field validation)

#### 16. Sighting timeline component (competitive P2 #7)

DRN-style horizontal time-axis timeline on the detection-detail screen.
Useful but not field-critical.

#### 17. Filmstrip thumbnail row in search results (competitive P2 #8)

Horizontal top-10 vehicle thumbnails above search results.

#### 18. Map zone drawing (competitive P2 #10)

Leaflet Draw integration so operators can define geographic search zones.

#### 19. PDF export from search (competitive P3 #12)

Map snapshot + result table + frequency scores.

#### 20. Watch this plate (competitive P3 #13)

User-defined plate subscriptions outside the formal hotlist.

## Recommended implementation order

Phases match what's actually shippable in one focused work session.

### Phase A — Half day (P0 fast wins)

1. Move `--critical / --cyan / --warn / --success / --muted` design tokens to
   a shared root (or fix the dashboard.css duplicates)
2. Replace `:::` drag handle with a real glyph
3. Add Escape key handler to the customize panel
4. Drop or replace the "RS" instrument brand mark

### Phase B — One day (P0 high-leverage)

5. Add `severity-band` classes to `CompactDetectionCard` and
   `RecentDetectionHistoryCard`
6. Host the existing `DetectionFeed` inside the dashboard `liveDetections`
   widget body so dashboard view inherits auto-scroll + pause + severity bands

### Phase C — Two days (P1 intelligence)

7. Frequency score computation + badge (most-visible intelligence
   improvement; close one big gap to DRN)
8. RecoveryStatePill component + threading through hit alert + recovery
   queue
9. Confirm Match / False Positive buttons + `C` / `F` keyboard shortcuts
   on the hit alert takeover

### Phase D — Polish (one more day)

10. Reduce customize-panel width to 40 %, transparent scrim
11. `Ctrl+1..5` layout-mode keyboard shortcuts
12. Status-pill typography scale via `--shift-mode-scale` CSS variable

### Phase E — File-organization refactor (do when nothing else is in flight)

13. Extract screens out of `App.tsx`
14. Split `styles.css` into the proposed file structure

## What I would NOT change

These are right as-is even though they look like obvious cuts:

- The five layout-mode presets — the spec calls for them, the customize
  panel exposes them, and the localStorage persistence works.
- The Operations / Admin shell split — it matches the spec exactly and
  the toolbar conventions are clean.
- The auto-scroll cadence (2,600 ms) and interaction lock (8 s) — those
  numbers are calibrated to the demo footage; do not tune without
  re-watching a recovery session.
- The dual-image evidence hero ratio — keeps plate-crop legible while
  showing color-overview at the size needed for visual confirmation.
- The Leaflet map stage — the route HUD work is recent and field-relevant.
- The hotlist alert takeover modal — already verification-gated per
  pro-grade strategy.

## What I would NOT autonomously do without your nod

- Touch the `apps/ui` build configuration or add new dependencies
- Refactor `App.tsx` into smaller files (high churn, fragile)
- Change the recovery-state model — that's a contract decision
- Modify the API contracts in `live-api.ts` for the frequency-score work;
  the score should be a derived UI computation first, then promoted to
  API later if it earns its place

## Open question for you

Do you want the polish work to land as one big PR ("UI polish — phases
A–C") or as four small commits along the phase boundaries? My
recommendation is **four small commits**: each phase is independently
shippable, the diffs are reviewable in 5–10 minutes each, and you can
stop after any phase if something else takes priority. But if the
preference is one bundled commit so the visual change is reviewed as a
whole, that works too.

## How I'll execute

If you greenlight, I will:

1. Implement phase A in a single commit, push, and report
2. Implement phase B and re-verify the dashboard view matches the
   pro-grade bar against the screenshot in the competitive doc
3. Implement phase C, including the new frequency-score computation +
   per-class verification on the existing detection corpus
4. Implement phase D and run `npm run build` (or whatever apps/ui's
   build script is) to confirm TypeScript passes
5. Phase E happens only if you explicitly ask — it's higher risk

I will NOT touch the 18 Codex UI files that are already in `507795f` —
those are committed. Polish lands on top.
