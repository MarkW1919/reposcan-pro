"""WhitePages Pro skip-trace provider (identity_check).

Calls the licensed, paid WhitePages Pro API and normalizes the response into
this app's Occupant model. The HTTP transport is injected so the parsing and
fallback/rate-limit logic are fully unit-testable without network access.

Compliance:
  * The API key is read from configuration (never hard-coded), sent only as a
    request parameter, and MASKED in the audit record — never logged in clear.
  * Every call returns a SkipTraceAudit (endpoint, masked params, HTTP status,
    success flag) for the coordinator to persist to the audit table.
  * 429 (rate limit) is honored: we wait (Retry-After, bounded) and retry once,
    then degrade rather than hammer the API.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from reposcan_contracts.occupant_intel import Occupant

from .base import AddressComponents, SkipTraceAudit, SkipTraceProvider, SkipTraceResult

WHITEPAGES_IDENTITY_CHECK_URL = "https://proapi.whitepages.com/3.1/identity_check"
_DEFAULT_TIMEOUT_S = 8.0
_MAX_RATE_LIMIT_WAIT_S = 3.0  # bounded so a field request never hangs
_USER_AGENT = "RepoScanPro-OccupantIntel/1.0 (authorized repossession field tool)"


@dataclass
class HttpJsonResponse:
    status: int
    payload: Optional[object]
    retry_after_s: Optional[float] = None


class HttpTransport(Protocol):
    def get(self, url: str, params: dict[str, str], *, timeout: float) -> HttpJsonResponse:
        ...


class UrllibTransport:
    """Stdlib transport. Exposes HTTP status + Retry-After for audit/rate-limit."""

    def get(self, url: str, params: dict[str, str], *, timeout: float = _DEFAULT_TIMEOUT_S) -> HttpJsonResponse:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        request = urllib.request.Request(f"{url}?{query}", method="GET")
        request.add_header("User-Agent", _USER_AGENT)
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted WhitePages host)
                raw = response.read().decode("utf-8", errors="replace")
            return HttpJsonResponse(status=200, payload=json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:  # 4xx/5xx with a status code
            retry_after = _parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
            payload = None
            try:
                body = exc.read().decode("utf-8", errors="replace")
                payload = json.loads(body) if body else None
            except (ValueError, OSError):
                payload = None
            return HttpJsonResponse(status=exc.code, payload=payload, retry_after_s=retry_after)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return HttpJsonResponse(status=0, payload=None)  # offline / no response


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "***"
    return f"***{api_key[-4:]}"


class WhitePagesProProvider(SkipTraceProvider):
    name = "WhitePages Pro"

    def __init__(
        self,
        api_key: str,
        *,
        transport: Optional[HttpTransport] = None,
        sleeper: Callable[[float], None] = None,  # type: ignore[assignment]
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        endpoint: str = WHITEPAGES_IDENTITY_CHECK_URL,
    ) -> None:
        self._api_key = api_key or ""
        self._transport = transport or UrllibTransport()
        self._sleeper = sleeper if sleeper is not None else _noop_sleep
        self._timeout_s = timeout_s
        self._endpoint = endpoint

    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        params = {
            "address_line_1": components.address_line_1 or "",
            "city": components.city or "",
            "state_code": components.state_code or "",
            "postal_code": components.postal_code or "",
            "api_key": self._api_key,
        }
        masked = {**params, "api_key": _mask_key(self._api_key)}

        response = self._transport.get(self._endpoint, params, timeout=self._timeout_s)

        # Honor rate limiting: one bounded wait + retry, then degrade.
        if response.status == 429:
            wait_s = min(response.retry_after_s or 1.0, _MAX_RATE_LIMIT_WAIT_S)
            self._sleeper(max(0.0, wait_s))
            response = self._transport.get(self._endpoint, params, timeout=self._timeout_s)
            if response.status == 429:
                return SkipTraceResult(
                    source=self.name,
                    ok=False,
                    audit=SkipTraceAudit(
                        endpoint=self._endpoint,
                        params_masked=masked,
                        http_status=429,
                        success=False,
                        rate_limited=True,
                        error="rate_limited",
                    ),
                )

        if response.status != 200 or not isinstance(response.payload, dict):
            return SkipTraceResult(
                source=self.name,
                ok=False,
                audit=SkipTraceAudit(
                    endpoint=self._endpoint,
                    params_masked=masked,
                    http_status=response.status or None,
                    success=False,
                    error=None if response.status == 200 else f"http_{response.status}" if response.status else "offline",
                ),
            )

        high_confidence, previous = _parse_identity_check(response.payload)
        return SkipTraceResult(
            source=self.name,
            ok=True,
            high_confidence=high_confidence,
            other_possible=[],
            previous_addresses=previous,
            audit=SkipTraceAudit(
                endpoint=self._endpoint,
                params_masked=masked,
                http_status=200,
                success=True,
            ),
        )


def _noop_sleep(_seconds: float) -> None:
    return None


def _parse_identity_check(payload: dict) -> tuple[list[Occupant], list[str]]:
    """Map an identity_check response to (high_confidence occupants, previous addrs)."""
    occupants: list[Occupant] = []
    for address in _as_list(payload.get("current_addresses")):
        if not isinstance(address, dict):
            continue
        for resident in _as_list(address.get("residents")):
            if not isinstance(resident, dict):
                continue
            occupant = _parse_resident(resident)
            if occupant is not None:
                occupants.append(occupant)

    previous: list[str] = []
    for address in _as_list(payload.get("previous_addresses")):
        formatted = _format_address(address)
        if formatted:
            previous.append(formatted)

    return occupants, previous


def _parse_resident(resident: dict) -> Optional[Occupant]:
    name = str(resident.get("name") or "").strip()
    if not name:
        return None
    phones = [
        _format_phone(phone)
        for phone in _as_list(resident.get("phones"))
        if isinstance(phone, dict)
    ]
    associated = [
        _format_associated(person)
        for person in _as_list(resident.get("associated_people"))
        if isinstance(person, dict)
    ]
    return Occupant(
        name=name,
        phones=[p for p in phones if p],
        associated_people=[a for a in associated if a],
    )


def _format_phone(phone: dict) -> str:
    number = str(phone.get("phone_number") or "").strip()
    if not number:
        return ""
    line_type = str(phone.get("line_type") or "").strip()
    return f"{number} ({line_type})" if line_type else number


def _format_associated(person: dict) -> str:
    name = str(person.get("name") or "").strip()
    if not name:
        return ""
    relation = str(person.get("relation") or "").strip()
    return f"{name} ({relation})" if relation else name


def _format_address(address: object) -> str:
    if not isinstance(address, dict):
        return ""
    line1 = str(address.get("address_line_1") or "").strip()
    city = str(address.get("city") or "").strip()
    state = str(address.get("state_code") or "").strip()
    postal = str(address.get("postal_code") or "").strip()
    city_state = ", ".join(p for p in (city, state) if p)
    locality = " ".join(p for p in (city_state, postal) if p).strip()
    return ", ".join(p for p in (line1, locality) if p)


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []
