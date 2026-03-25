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

## Headless Ingest Simulation

1. Open `Recovery Alerts`
2. In `Quick Actions`, enter a local frame folder path and leave the selected alert plate or replace it with a demo plate
3. If you want frame-specific outputs, place sibling `*.inference.json` files next to the `.jpg` frames before running the demo
4. Optionally validate the runtime stack first with `.\.venv\Scripts\python.exe .\scripts\validate_model_stack.py --model-config .\configs\models\local-onnx-runtime.yaml`
5. Click `Run headless demo`
6. Confirm the status changes to `Running`, then to `Ready`
7. Confirm preprocessing artifacts appear under `runtime/preprocessed` or the configured preprocessing output folder
8. Confirm new live detections appear without restarting the API
9. Select the new alert and confirm the target card shows a live evidence frame and, when available, a plate crop preview
10. If an active hotlist entry matches the simulated plate, confirm a new alert appears in `Recovery Alerts`
11. If you intentionally want the builtin fallback instead of ONNX fixtures, rerun the flow with `--model-config .\configs\models\local-demo-runtime.yaml`

## Headless Ingest CLI Fallback

1. With the API still running, open a new terminal in the repo
2. Run `.\.venv\Scripts\python.exe .\scripts\run_file_sequence_demo.py --frames-dir C:\path\to\frame-folder`
3. Confirm the script reports captured frames, finalized tracks, and at least one stored detection
4. Confirm the default model config is `configs/models/local-onnx-runtime.yaml` unless you override `--model-config`

## Hotlist Management

1. Stay in `Field Settings`
2. Confirm the hotlist manager loads the seeded live API hotlist entries
3. Select an existing hotlist entry and change its label, notes, or active state
4. Save the update and confirm the success message appears
5. Click `New entry` or `Seed from selected alert` and create a new hotlist entry
6. Refresh the page and confirm the new or updated hotlist entry remains visible from the live API

## Alert Response Workflow

1. Open `Recovery Alerts` and keep the live API connected
2. Select an active alert, then open `Quick Actions`
3. Enter an operator ID and optional response notes
4. Click `Acknowledge` and confirm the success message appears
5. Refresh the page and confirm the alert still shows the updated workflow state
6. Click `Stand down` and confirm the alert drops out of `Live popup activity`
7. Click `Re-open` and confirm the alert returns to active monitoring state

## Review Loop

1. Select the primary alert and open the target card
2. Confirm the card shows live review history when the API is connected
3. Submit a `Confirm read`, `Flag for follow-up`, or `Correct read` review
4. If using `Correct read`, enter a corrected plate value before saving
5. Confirm the success message appears and the new review is inserted at the top of the review history
6. Refresh the page and confirm the saved review remains visible from the live API

## Evidence Export And Maintenance

1. In a new terminal, run `.\.venv\Scripts\python.exe .\scripts\run_storage_maintenance.py --deployment-config .\configs\deployments\local-dev.yaml --json`
2. Confirm the output reports both `storage_pressure` and `retention`
3. Pick a live or seeded detection ID such as `det_20260320_010001`
4. Run `.\.venv\Scripts\python.exe .\scripts\export_detection_package.py --detection-id det_20260320_010001 --deployment-config .\configs\deployments\local-dev.yaml --json`
5. Confirm the export zip path is returned
6. Confirm the zip contains `manifest.json` and any available evidence files

## Remote Sync And Alert Delivery Evidence

1. In a new terminal, run `.\.venv\Scripts\python.exe .\scripts\generate_sync_remote_evidence.py --output-root .\services\sync\fixtures --overwrite`
2. Confirm the script reports:
   - `first_run_failed=1`
   - `retry_run_synced=1`
   - `idempotent_replay_synced=1`
3. Open `services/sync/fixtures/reports/remote-sync-validation.json`
4. Confirm:
   - `remote_unique_detections = 1`
   - `remote_sync_posts = 3`
   - `final_sync_status = synced`
   - `remote_unique_alerts = 1`
   - `remote_alert_posts = 2`

## Validation Commands

- `.\.venv\Scripts\python.exe -m pytest -q`
- `npm run ui:build`
- `npm run check`
