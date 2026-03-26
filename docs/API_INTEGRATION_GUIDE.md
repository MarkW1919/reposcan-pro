# API_INTEGRATION_GUIDE.md

This document is the practical integration guide for the RepoScan Pro API.

Use it when another service, a secured operator client, or an automation job needs
to call the API without guessing at route shape, auth behavior, or compatibility rules.

## Canonical Base Path

The canonical external API surface is versioned under:

- `/api/v1`

Compatibility aliases without the version prefix still exist when
`deployment.api.versioning.enable_legacy_routes` is `true`, but new integrations
should treat `/api/v1` as the stable contract base.

Use `GET /api/v1/version` to confirm:

- package version
- current API version
- canonical prefix
- whether legacy aliases are enabled
- whether auth and rate limiting are active

## Public Versus Protected Routes

By default:

- `GET /api/v1/health` may remain public
- `GET /api/v1/version` may remain public

Everything else should be treated as protected when API security is enabled.

## Authentication

When `deployment.api.security.enabled` is `true`, callers must provide either:

- `X-RepoScan-Api-Key: <token>`
- `Authorization: Bearer <token>`

The configured header name can be changed with `deployment.api.security.api_key_header`.

The repository ships an example-only secure profile at:

- `configs/deployments/local-secure-api-example.yaml`

Those committed tokens are for local testing only and must be replaced in private deployment copies.

## Authorization Roles

The API currently uses four coarse roles:

- `viewer`: read dashboard, detections, alerts, reviews, hotlists, and search
- `operator`: submit reviews, manage follow-ups and dispatch assignments, update alert lifecycle state, and start demo runs
- `admin`: create and update hotlists
- `integrator`: read audit events

`admin` is also allowed to read audit events.

## Search Endpoints

Detection search:

- `GET /api/v1/search/detections`

Supported filters:

- `plate`
- `plate_match` with `contains`, `exact`, `prefix`, or `suffix`
- `start_utc`
- `end_utc`
- `camera_id`
- `min_latitude`
- `max_latitude`
- `min_longitude`
- `max_longitude`
- `vehicle_color`
- `vehicle_make`
- `vehicle_model`
- `vehicle_year`
- `alert_status`
- `limit`
- `offset`

Alert search:

- `GET /api/v1/search/alerts`

Supported filters:

- `plate`
- `plate_match`
- `start_utc`
- `end_utc`
- `camera_id`
- `min_latitude`
- `max_latitude`
- `min_longitude`
- `max_longitude`
- `vehicle_color`
- `vehicle_make`
- `vehicle_model`
- `vehicle_year`
- `status`
- `limit`
- `offset`

Both search endpoints return:

- `page.total_results`
- `page.limit`
- `page.offset`
- `results`

## Audit Surface

The API is the audit boundary for operator-visible mutations and secured search actions.

Read recent audit events with:

- `GET /api/v1/audit/events`

Supported filters:

- `limit`
- `principal_id`
- `action_prefix`
- `outcome`
- `target_id`

Current audited success actions include:

- `search.detections`
- `search.alerts`
- `review.create`
- `follow_up.create`
- `follow_up.update`
- `assignment.create`
- `assignment.update`
- `alert.update`
- `hotlist.create`
- `hotlist.update`
- `demo.run.start`

Denied auth, role failures, and rate-limit failures are also recorded when audit logging is enabled.

## Rate Limiting And Hardening

Request throttling is controlled by:

- `deployment.api.rate_limit.enabled`
- `deployment.api.rate_limit.requests_per_minute`

Responses include:

- `X-Request-Id`
- `X-Api-Version`
- `X-RateLimit-Limit` when throttling is active
- `X-RateLimit-Remaining` when throttling is active

Rate-limited responses return:

- HTTP `429`
- `Retry-After`

The API also adds baseline hardening headers when enabled:

- `Cache-Control: no-store`
- `Referrer-Policy: no-referrer`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`

Trusted hosts are controlled by:

- `deployment.api.hardening.trusted_hosts`

OpenAPI and docs exposure are controlled by:

- `deployment.api.hardening.expose_docs`

## Example Calls

Read version info:

```powershell
curl http://127.0.0.1:8000/api/v1/version
```

Search detections with a secured viewer token:

```powershell
curl `
  -H "X-RepoScan-Api-Key: viewer-demo-token" `
  "http://127.0.0.1:8000/api/v1/search/detections?plate=6BZN&plate_match=prefix&camera_id=cam_north_gate_01"
```

Update an alert with an operator token:

```powershell
curl `
  -X PUT `
  -H "Content-Type: application/json" `
  -H "X-RepoScan-Api-Key: operator-demo-token" `
  -d '{"status":"acknowledged","response_notes":"Operator visually confirmed the vehicle."}' `
  "http://127.0.0.1:8000/api/v1/alerts/alert_001"
```

Read audit events with an admin token:

```powershell
curl `
  -H "X-RepoScan-Api-Key: admin-demo-token" `
  "http://127.0.0.1:8000/api/v1/audit/events?action_prefix=hotlist"
```

## Integration Policy

- prefer `/api/v1` routes for all new consumers
- treat unversioned routes as compatibility aliases, not the primary contract
- keep callers resilient to `401`, `403`, `404`, `409`, and `429`
- preserve `X-Request-Id` in client logs so operator actions can be matched to audit events
- do not scrape local media paths directly; use the API media endpoints

## Related Documents

- [API Contracts](API_CONTRACTS.md)
- [Deployment](DEPLOYMENT.md)
- [Operations And Logging](OPERATIONS_AND_LOGGING.md)
