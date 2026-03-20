# UI App

Host the operator-facing client for live monitoring, search, review, and alert response.

Current preview slice:
- dark operator-console UI tuned for repossession agents using Windows 11 laptops in the cab
- route HUD, recovery alerts, camera views, field settings, and a customizable dashboard workspace
- browser-persisted layout presets for map, camera, alert feed, and target-card placement
- address-based scan mode with arrival-radius activation, operator override, and live API popup activity when available
- always-on hotlist popup behavior that stays active regardless of navigation or address-scan state
- live API overview integration with graceful fallback to local demo data when the backend is offline
- demo-friendly repo workflows while backend and hardware integration continue

Local development notes:
- the UI will try `http://127.0.0.1:8000/dashboard/overview` by default
- set `VITE_API_BASE_URL` if the API is running elsewhere
