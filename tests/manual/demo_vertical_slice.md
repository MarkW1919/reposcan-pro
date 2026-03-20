# Demo Vertical Slice Checklist

Use this checklist when validating the current integrated API + UI demo path on a Windows 11 development laptop.

## Goal

Confirm that the seeded local API and the cab-first UI behave like a usable repossession operator demo even before target hardware arrives.

## Start The Stack

1. Run `npm run api:dev`
2. In a second terminal, run `npm run ui:dev`
3. Open `http://127.0.0.1:4173`

## Expected Startup State

- the UI loads without build errors
- the top status band shows `Live API connected` when the API is running
- the dashboard renders seeded detections, alerts, and hotlist counts from the API
- if the API is stopped, the UI falls back to demo data instead of crashing

## Route And Scan Flow

1. Open `Route HUD` or the route panel on the dashboard
2. Confirm a destination is visible and `Start navigation` is available
3. Start navigation
4. Move the arrival slider so the current distance is greater than the arrival ring
5. Confirm the UI reports that general detections are suppressed or background-only outside the radius
6. Move the slider inside the arrival ring
7. Confirm the UI switches into active scan behavior and surfaces general popup alerts

## Operator Override

1. While inside the arrival radius, toggle `Address detection` off
2. Confirm general popup alerts stop appearing
3. Confirm the banner explains that address-based popup detection is disabled by the operator
4. Toggle `Address detection` back on
5. Confirm general popup alerts resume while still inside the radius

## Hotlist Behavior

1. Leave navigation inactive or disable address detection
2. Wait for the next hotlist popup
3. Confirm a hotlist popup still appears
4. Confirm it is styled as high priority and indicates visual or audible behavior
5. Confirm the banner and status areas still describe hotlist alerting as always active

## Data Integration

1. Open `Recovery Alerts`
2. Confirm alert rows reflect live API-seeded alert records
3. Confirm `Live popup activity` renders entries from the active popup stream
4. Open `Field Settings`
5. Confirm layout changes persist in the browser after refresh

## Validation Commands

- `.\.venv\Scripts\python.exe -m pytest -q`
- `npm run ui:build`
- `npm run check`
