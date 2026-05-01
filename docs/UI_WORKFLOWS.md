# UI_WORKFLOWS.md

The operator experience should support fast decision-making under field conditions, not only retrospective analytics.

## Live Monitoring

- show current camera status and ingest health
- surface active detections with image previews and confidence
- elevate hotlist hits immediately with location and timestamp context
- keep the map usable as a first-class operator surface, including current unit position, compact current-location address context, and destination guidance without leaving the console

## Review Workflow

- inspect the source frame and the plate crop side by side
- inspect alternate OCR candidates and stored confidence breakdowns before escalating a hit
- edit OCR results when operator review is required
- mark false positives and preserve audit history
- pin high-value detections for follow-up
- keep follow-up owner, status, due time, and notes visible on the selected target

## Search Workflow

- search by full or partial plate
- filter by date, camera, GPS region, color, make/model, and alert state
- jump from search results into detailed review
- keep pinned follow-up and dispatch state visible in search results

## Recovery Account Intake

- create a recovery account from plate, VIN, or vehicle make and model
- attach a target address, lot label, and recovery instructions to the account
- make it explicit when a record is intake-only versus ready for live plate alerting
- allow operators to open account management without routing through the active case queue
- support routing workflows through lightweight address lookup and reverse-geocode context, without depending on the removed advanced local enrichment feature set

## Alert Workflow

- display alert severity, plate read, and confidence
- show camera ID, GPS location, and time
- preserve a durable record of alert acknowledgement and response
- support acknowledge, stand down, and reopen actions without losing context on the selected target
- suppress dismissed alerts from the live popup stream while keeping the status visible in history
- create and update dispatch assignments that persist beyond the alert status buttons

## Operator Awareness

- show the current operator identity and granted roles when auth is active
- gate mutation workflows in the UI based on role permissions instead of waiting for a failed request
- show other active console sessions, their current workspace, and their selected target context

## Related Documents

- [API Contracts](API_CONTRACTS.md)
- [Driver Mobile UI Wireframe Spec](DRIVER_MOBILE_UI_WIREFRAME_SPEC.md)
- [Product](PRODUCT.md)
- [Requirements](REQUIREMENTS.md)
