## UI Dashboard Refactor Plan

### Goal
Refine the existing `apps/ui` dashboard into a repossession-focused recovery console with a Ram-inspired instrument-cluster and center-screen layout while preserving all current routing, LPR, map, hotlist, follow-up, and API behavior.

### Frontend Audit
- Active frontend app: `apps/ui`
- Main app entry: `apps/ui/src/App.tsx`
- Global styles: `apps/ui/src/styles.css`
- Live API/types: `apps/ui/src/live-api.ts`
- Existing live detection list: `apps/ui/src/components/console/DetectionFeed.tsx`
- Existing compact row UI: `apps/ui/src/components/console/DetectionFeedRow.tsx`
- Existing evidence media panel: `apps/ui/src/components/detections/DetectionEvidenceHero.tsx`
- Existing map/navigation logic: `MapStagePanel`, `OpsMap`, destination modal, route/session logic in `App.tsx`
- Existing camera rendering: `CameraViewport` in `App.tsx`
- Existing search/address intelligence panel: `SearchLeadPanel` in `App.tsx`
- Existing state management: local `useState` in `App.tsx` plus existing localStorage-backed settings and route state

### Functionality To Preserve
- Dashboard overview polling and fallback/demo handling
- Existing map/navigation destination selection and route flow
- Existing LPR scan state and edge runtime status
- Existing detection selection, detail overlay, and review flow
- Existing hotlist/account, follow-up, and recovery alert flows
- Existing camera feed selection and live image loading
- Existing auth/API key flow and backend contracts
- Existing non-console screens: search, accounts, recoveries, settings

### Files To Modify
- `apps/ui/src/App.tsx`
- `apps/ui/src/main.tsx`
- `apps/ui/src/styles.css`

### Files To Add
- `apps/ui/src/dashboard.css`
- `apps/ui/src/dashboard-config.ts`
- `apps/ui/src/components/dashboard/DashboardShell.tsx`
- `apps/ui/src/components/dashboard/InstrumentStatusBar.tsx`
- `apps/ui/src/components/dashboard/UconnectStyleToolbar.tsx`
- `apps/ui/src/components/dashboard/DashboardWidgetFrame.tsx`
- `apps/ui/src/components/dashboard/DashboardCustomizePanel.tsx`
- `apps/ui/src/components/dashboard/StatusPill.tsx`
- `apps/ui/src/components/dashboard/CompactDetectionCard.tsx`
- `apps/ui/src/components/dashboard/LprCameraPanel.tsx`
- `apps/ui/src/components/dashboard/AddressIntelligenceCard.tsx`
- `apps/ui/src/components/dashboard/RecentDetectionHistoryCard.tsx`

### Refactor Strategy
1. Keep the existing `App.tsx` data/state logic intact.
2. Add a typed dashboard configuration store persisted to localStorage.
3. Replace the current console screen composition with a new configurable shell.
4. Reuse existing map, camera, detection, hotlist, and detail actions through props.
5. Keep the bottom navigation model, but restyle it into a Ram/Uconnect-style toolbar.
6. Leave search/accounts/recoveries/settings workflows intact except for shared toolbar styling.

### New Dashboard Modules
- Instrument-style top status bar
- Uconnect-style navigation toolbar
- Dominant map/navigation widget
- Address intelligence widget
- AI insight widget
- Compact live detections widget
- Two-camera LPR widget
- Recent detection history widget
- Route summary widget
- Notes widget backed by existing account/follow-up notes when available

### Dashboard Config Strategy
- Storage key: `reprovision.dashboard.config.v1`
- Type-safe config module with:
  - `getDefaultDashboardConfig()`
  - `loadDashboardConfig()`
  - `saveDashboardConfig()`
  - `resetDashboardConfig()`
  - `updateWidgetVisibility()`
  - `updateWidgetSize()`
  - `updateLayoutMode()`
- Modes:
  - `default`
  - `driving`
  - `scanning`
  - `review`
  - `minimal`

### Testing Plan
- Run `npm run build` in `apps/ui`
- Confirm TypeScript passes through build command
- If additional scripts are present for UI checks, run them only if already defined
- Manually verify that console/search/accounts/recoveries/settings still render from the existing navigation flow

### Out Of Scope
- Backend contract changes
- Training, inference, dataset, checkpoint, or model-pipeline changes
- New dependencies for drag-and-drop or large state-management rewrites
