# UI_WORKFLOWS.md

The operator experience should support fast decision-making under field conditions, not only retrospective analytics.

## Live Monitoring

- show current camera status and ingest health
- surface active detections with image previews and confidence
- elevate hotlist hits immediately with location and timestamp context

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
