"""WhitePages person/skip-trace provider (api.whitepages.com/v2/person).

Resolves the people associated with an address. The HTTP transport is injected
so parsing and fallback/rate-limit logic are fully unit-testable without
network access.

API shape (confirmed live):
  GET https://api.whitepages.com/v2/person?street=&city=&state_code=&postal_code=
  Header: X-Api-Key: <key>
  Response: { "results": [ { name, phones:[{number,type,score}], relatives:[...],
              current_addresses:[...], historic_addresses:[...], match_score } ],
             "metadata": {...} }

Compliance:
  * The API key is read from configuration (never hard-coded), sent only in the
    X-Api-Key header, and never logged — the audit records a masked fingerprint.
  * Every call returns a SkipTraceAudit (endpoint, masked params, HTTP status,
    success flag) for the coordinator to persist to the audit table.
  * 429 (rate limit) is honored: bounded wait + single retry, then degrade.
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

WHITEPAGES_PERSON_URL = "https://api.whitepages.com/v2/person"
_DEFAULT_TIMEOUT_S = 10.0
_MAX_RATE_LIMIT_WAIT_S = 3.0  # bounded so a field request never hangs
_USER_AGENT = "RepoScanPro-OccupantIntel/1.0 (authorized repossession field tool)"

# Display caps so the in-cab card stays glanceable (no clutter).
_MAX_HIGH_CONFIDENCE = 6
_MAX_OTHER_POSSIBLE = 6
_MAX_PHONES = 4
_MAX_ASSOCIATED = 6
_MAX_PREVIOUS = 12
# A match is "high confidence" if its score is within this fraction of the best
# match's score (robust to the absolute score scale, which varies by plan).
_HIGH_CONFIDENCE_FRACTION = 0.7


@dataclass
class HttpJsonResponse:
    status: int
    payload: Optional[object]
    retry_after_s: Optional[float] = None


class HttpTransport(Protocol):
    def get(
        self, url: str, params: dict[str, str], *, headers: Optional[dict[str, str]] = None, timeout: float
    ) -> HttpJsonResponse:
        ...


class UrllibTransport:
    """Stdlib transport. Exposes HTTP status + Retry-After for audit/rate-limit."""

    def get(
        self,
        url: str,
        params: dict[str, str],
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> HttpJsonResponse:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
        request = urllib.request.Request(f"{url}?{query}", method="GET")
        request.add_header("User-Agent", _USER_AGENT)
        request.add_header("Accept", "application/json")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted WhitePages host)
                raw = response.read().decode("utf-8", errors="replace")
            return HttpJsonResponse(status=200, payload=json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:  # 4xx/5xx with a status code
            retry_after = _parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
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
        endpoint: str = WHITEPAGES_PERSON_URL,
    ) -> None:
        self._api_key = api_key or ""
        self._transport = transport or UrllibTransport()
        self._sleeper = sleeper if sleeper is not None else _noop_sleep
        self._timeout_s = timeout_s
        self._endpoint = endpoint

    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        params = {
            "street": components.address_line_1 or "",
            "city": components.city or "",
            "state_code": components.state_code or "",
            # API requires a strict 5-digit zipcode (^\d{5}$); omit if not clean.
            "zipcode": _zip5(components.postal_code),
            # Populate each person's previous addresses for skip-tracing.
            "include_historical_locations": "true",
        }
        headers = {"X-Api-Key": self._api_key}
        # Audit shows the query + a masked key fingerprint (key travels in the
        # header and is never recorded in the clear).
        masked = {**params, "api_key": _mask_key(self._api_key)}

        response = self._transport.get(self._endpoint, params, headers=headers, timeout=self._timeout_s)

        # Honor rate limiting: one bounded wait + retry, then degrade.
        if response.status == 429:
            wait_s = min(response.retry_after_s or 1.0, _MAX_RATE_LIMIT_WAIT_S)
            self._sleeper(max(0.0, wait_s))
            response = self._transport.get(self._endpoint, params, headers=headers, timeout=self._timeout_s)
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
                    error=f"http_{response.status}" if response.status else "offline",
                ),
            )

        high_confidence, other_possible, previous = _parse_person_results(response.payload)
        return SkipTraceResult(
            source=self.name,
            ok=True,
            high_confidence=high_confidence,
            other_possible=other_possible,
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


def _zip5(postal: Optional[str]) -> str:
    """Return a clean 5-digit ZIP (handles ZIP+4) or '' if not derivable."""
    if not postal:
        return ""
    digits = "".join(ch for ch in postal if ch.isdigit())
    return digits[:5] if len(digits) >= 5 else ""


@dataclass
class _ScoredPerson:
    occupant: Occupant
    score: float
    historic: list[str]


def _parse_person_results(payload: dict) -> tuple[list[Occupant], list[Occupant], list[str]]:
    """Map a /v2/person response to (high_confidence, other_possible, previous)."""
    people: list[_ScoredPerson] = []
    for result in _as_list(payload.get("results")):
        if not isinstance(result, dict):
            continue
        person = _parse_person(result)
        if person is not None:
            people.append(person)

    if not people:
        return [], [], []

    # Rank by match strength, then split into strong matches vs weaker maybes.
    people.sort(key=lambda p: p.score, reverse=True)
    best = people[0].score
    cutoff = best * _HIGH_CONFIDENCE_FRACTION if best > 0 else 0.0
    high = [p for p in people if p.score >= cutoff][:_MAX_HIGH_CONFIDENCE]
    high_ids = {id(p) for p in high}
    other = [p for p in people if id(p) not in high_ids][:_MAX_OTHER_POSSIBLE]

    # Previous addresses: aggregate the strong matches' history (deduped).
    previous: list[str] = []
    seen: set[str] = set()
    for person in high:
        for address in person.historic:
            key = address.lower()
            if address and key not in seen:
                seen.add(key)
                previous.append(address)
            if len(previous) >= _MAX_PREVIOUS:
                break
        if len(previous) >= _MAX_PREVIOUS:
            break

    return [p.occupant for p in high], [p.occupant for p in other], previous


def _parse_person(result: dict) -> Optional[_ScoredPerson]:
    name = str(result.get("name") or "").strip()
    if not name:
        return None

    phones = []
    for phone in _as_list(result.get("phones")):
        formatted = _format_phone(phone)
        if formatted:
            phones.append(formatted)
        if len(phones) >= _MAX_PHONES:
            break

    associated = []
    for relative in _as_list(result.get("relatives")):
        formatted = _format_relative(relative)
        if formatted:
            associated.append(formatted)
        if len(associated) >= _MAX_ASSOCIATED:
            break

    historic = [a for a in (_format_address(addr) for addr in _as_list(result.get("historic_addresses"))) if a]

    try:
        score = float(result.get("match_score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    return _ScoredPerson(
        occupant=Occupant(name=name, phones=phones, associated_people=associated),
        score=score,
        historic=historic,
    )


def _format_phone(phone: object) -> str:
    if not isinstance(phone, dict):
        return ""
    number = str(phone.get("number") or "").strip()
    if not number:
        return ""
    line_type = str(phone.get("type") or "").strip()
    return f"{number} ({line_type.title()})" if line_type else number


def _format_relative(relative: object) -> str:
    if isinstance(relative, str):
        return relative.strip()
    if not isinstance(relative, dict):
        return ""
    name = str(relative.get("name") or "").strip()
    if not name:
        return ""
    relation = str(relative.get("relation") or relative.get("relationship") or "").strip()
    return f"{name} ({relation})" if relation else name


def _format_address(address: object) -> str:
    if isinstance(address, str):
        return address.strip()
    if not isinstance(address, dict):
        return ""
    full = str(address.get("full_address") or "").strip()
    if full:
        return full
    line1 = str(address.get("line1") or address.get("address_line_1") or "").strip()
    city = str(address.get("city") or "").strip()
    state = str(address.get("state") or address.get("state_code") or "").strip()
    postal = str(address.get("zip") or address.get("postal_code") or "").strip()
    city_state = ", ".join(p for p in (city, state) if p)
    locality = " ".join(p for p in (city_state, postal) if p).strip()
    return ", ".join(p for p in (line1, locality) if p)


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []
