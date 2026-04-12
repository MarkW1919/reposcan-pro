"""Authentication, authorization, and request-throttling helpers."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException, Request, status

from reposcan_contracts.config.deployment import ApiConfig, ApiRole

from .audit import ApiAuditLogger
from .models import ApiAuditEvent, AuditOutcome


@dataclass(frozen=True)
class ApiPrincipalContext:
    principal_id: str
    roles: tuple[ApiRole, ...]
    authenticated: bool
    display_name: str | None = None


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int | None = None


class ApiRateLimiter:
    def __init__(self, *, requests_per_minute: int) -> None:
        self.requests_per_minute = requests_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def consume(self, key: str) -> RateLimitDecision:
        now = time.monotonic()
        window_start = now - 60.0
        with self._lock:
            events = self._events[key]
            while events and events[0] < window_start:
                events.popleft()
            if len(events) >= self.requests_per_minute:
                retry_after = max(1, int(events[0] + 60.0 - now))
                return RateLimitDecision(
                    allowed=False,
                    limit=self.requests_per_minute,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )
            events.append(now)
            remaining = max(0, self.requests_per_minute - len(events))
            return RateLimitDecision(
                allowed=True,
                limit=self.requests_per_minute,
                remaining=remaining,
            )


class ApiAccessController:
    _local_roles = (
        ApiRole.viewer,
        ApiRole.operator,
        ApiRole.admin,
        ApiRole.integrator,
    )
    _viewer_roles = (
        ApiRole.viewer,
        ApiRole.operator,
        ApiRole.admin,
        ApiRole.integrator,
    )
    _operator_roles = (ApiRole.operator, ApiRole.admin)
    _admin_roles = (ApiRole.admin,)
    _audit_roles = (ApiRole.integrator, ApiRole.admin)

    def __init__(self, config: ApiConfig, *, audit_logger: ApiAuditLogger | None = None) -> None:
        self.config = config
        self.audit_logger = audit_logger
        self._principals = {
            principal.api_key: principal
            for principal in self.config.security.principals
        }
        self._rate_limiter = ApiRateLimiter(requests_per_minute=config.rate_limit.requests_per_minute)

    def _request_id(self, request: Request) -> str:
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = request.headers.get("X-Request-Id") or f"req_{uuid4().hex[:12]}"
            request.state.request_id = request_id
        return request_id

    def _public_context(self) -> ApiPrincipalContext:
        return ApiPrincipalContext(
            principal_id="public",
            roles=(),
            authenticated=False,
        )

    def _local_context(self) -> ApiPrincipalContext:
        return ApiPrincipalContext(
            principal_id="local_dev",
            roles=self._local_roles,
            authenticated=False,
            display_name="Local Development",
        )

    def _extract_token(self, request: Request) -> str | None:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            scheme, _, token = auth_header.partition(" ")
            if scheme.lower() == "bearer" and token:
                return token.strip()
        header_name = self.config.security.api_key_header
        return request.headers.get(header_name)

    def _record_denied_event(
        self,
        *,
        request: Request,
        action: str,
        outcome: AuditOutcome,
        detail: str,
        principal_id: str | None = None,
        principal_roles: tuple[ApiRole, ...] = (),
    ) -> None:
        if self.audit_logger is None:
            return
        self.audit_logger.record(
            ApiAuditEvent(
                event_id=f"audit_{uuid4().hex[:12]}",
                occurred_at_utc=request.state.utcnow(),
                request_id=self._request_id(request),
                principal_id=principal_id,
                principal_roles=[role.value for role in principal_roles],
                action=action,
                outcome=outcome,
                method=request.method,
                path=request.url.path,
                details={"detail": detail},
            )
        )

    def _enforce_rate_limit(self, request: Request, *, key: str) -> None:
        if not self.config.rate_limit.enabled:
            return
        decision = self._rate_limiter.consume(key)
        request.state.rate_limit_limit = decision.limit
        request.state.rate_limit_remaining = decision.remaining
        if not decision.allowed:
            self._record_denied_event(
                request=request,
                action="rate_limit.denied",
                outcome=AuditOutcome.denied,
                detail="Request rate exceeded configured limit.",
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(decision.retry_after_seconds or 60)},
            )

    def _authenticate(self, request: Request) -> ApiPrincipalContext:
        if not self.config.security.enabled:
            context = self._local_context()
            request.state.principal = context
            self._enforce_rate_limit(request, key=f"local:{request.client.host if request.client else 'unknown'}")
            return context

        token = self._extract_token(request)
        if not token:
            self._record_denied_event(
                request=request,
                action="auth.denied",
                outcome=AuditOutcome.denied,
                detail="Missing API credentials.",
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API credentials")

        principal = self._principals.get(token)
        if principal is None:
            self._record_denied_event(
                request=request,
                action="auth.denied",
                outcome=AuditOutcome.denied,
                detail="Invalid API credentials.",
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API credentials")

        context = ApiPrincipalContext(
            principal_id=principal.principal_id,
            roles=tuple(principal.roles),
            authenticated=True,
            display_name=principal.display_name,
        )
        request.state.principal = context
        self._enforce_rate_limit(request, key=f"principal:{principal.principal_id}")
        return context

    def _authorize(
        self,
        request: Request,
        *,
        accepted_roles: tuple[ApiRole, ...],
        action: str,
    ) -> ApiPrincipalContext:
        principal = self._authenticate(request)
        if not any(role in accepted_roles for role in principal.roles):
            self._record_denied_event(
                request=request,
                action=action,
                outcome=AuditOutcome.denied,
                detail="Authenticated principal lacks the required role.",
                principal_id=principal.principal_id,
                principal_roles=principal.roles,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for this endpoint")
        return principal

    def health_access(self, request: Request) -> ApiPrincipalContext:
        if self.config.security.enabled and not self.config.security.allow_unauthenticated_health:
            return self._authorize(request, accepted_roles=self._viewer_roles, action="health.read")
        self._enforce_rate_limit(request, key=f"public:{request.client.host if request.client else 'unknown'}")
        return self._public_context() if self.config.security.enabled else self._local_context()

    def version_access(self, request: Request) -> ApiPrincipalContext:
        if self.config.security.enabled and not self.config.security.allow_unauthenticated_version:
            return self._authorize(request, accepted_roles=self._viewer_roles, action="version.read")
        self._enforce_rate_limit(request, key=f"public:{request.client.host if request.client else 'unknown'}")
        return self._public_context() if self.config.security.enabled else self._local_context()

    def address_search_access(self, request: Request) -> ApiPrincipalContext:
        self._enforce_rate_limit(request, key=f"public:{request.client.host if request.client else 'unknown'}")
        return self._public_context() if self.config.security.enabled else self._local_context()

    def viewer_access(self, request: Request) -> ApiPrincipalContext:
        return self._authorize(request, accepted_roles=self._viewer_roles, action="api.read")

    def operator_access(self, request: Request) -> ApiPrincipalContext:
        return self._authorize(request, accepted_roles=self._operator_roles, action="api.operator")

    def admin_access(self, request: Request) -> ApiPrincipalContext:
        return self._authorize(request, accepted_roles=self._admin_roles, action="api.admin")

    def audit_access(self, request: Request) -> ApiPrincipalContext:
        return self._authorize(request, accepted_roles=self._audit_roles, action="audit.read")


def principal_details(principal: ApiPrincipalContext | None) -> tuple[str | None, list[str]]:
    if principal is None:
        return None, []
    return principal.principal_id, [role.value for role in principal.roles]
