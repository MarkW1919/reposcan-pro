# UI App

Host the operator-facing client for live monitoring, search, review, and alert response.

Current preview slice:
- dark operator-console UI tuned for repossession agents using Windows 11 laptops in the cab
- route HUD, recovery alerts, search, camera views, field settings, and a customizable dashboard workspace
- browser-persisted layout presets for map, camera, alert feed, and target-card placement
- address-based scan mode with arrival-radius activation, operator override, and live API popup activity when available
- selected-alert evidence preview that shows a live frame and plate crop when local media is available through the API
- live detection search with full or partial plate lookup plus date, camera, GPS region, attribute, and alert-state filters
- selected-target detail view with alternate OCR candidates and stored confidence breakdowns from live detections
- field-settings hotlist manager for creating, editing, pausing, and seeding local hotlist entries from the selected alert
- quick-actions alert response controls for acknowledge, stand down, and reopen state changes when the live API is available
- selected-alert review history and local review submission when the live API is available
- quick-actions demo runtime controls for launching headless ingest runs from a local frame folder when the live API is available
- always-on hotlist popup behavior that stays active regardless of navigation or address-scan state
- live API overview integration with graceful fallback to local demo data when the backend is offline
- demo-friendly repo workflows while backend and hardware integration continue

Local development notes:
- the UI will try `http://127.0.0.1:8000/api/v1/dashboard/overview` by default
- set `VITE_API_BASE_URL` if the API is running elsewhere
- set `VITE_API_PREFIX` only if the API versioned prefix differs from `/api/v1`
