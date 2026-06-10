"""Enformion / EnformionGO skip-trace provider (POST /PersonSearch).

Enformion returns per-address residency date ranges (FirstReportedDate /
LastReportedDate) — the "Jan 2015 – Present" data WhitePages lacks. Auth is an
Access Profile NAME + PASSWORD pair sent as galaxy-ap-name / galaxy-ap-password
headers (NOT a single key). The HTTP transport is injected so parsing is
unit-testable without the live key.

Compliance mirrors the WhitePages provider: credentials never logged (password
masked in audit), best-effort (never raises), 429 honored.

NOTE: parsing is built to Enformion's documented schema; field nuances (persons
wrapper casing, phone/relative object shapes) should be confirmed with one live
call once ENFORMION_AP_NAME is set, and adjusted if the real payload differs.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from reposcan_contracts.occupant_intel import Occupant, PreviousAddress

from .base import AddressComponents, SkipTraceAudit, SkipTraceProvider, SkipTraceResult
from .whitepages_pro import HttpJsonResponse, _parse_retry_after  # reuse shared types/helpers

# NOTE: the API host is devapi.enformion.com — api.enformion.com is the
# marketing site (404s). Enformion fronts the API with Cloudflare, which 1010-
# blocks non-browser user-agents, so we present a standard browser UA.
ENFORMION_PERSON_SEARCH_URL = "https://devapi.enformion.com/PersonSearch"
_DEFAULT_TIMEOUT_S = 12.0
_MAX_RATE_LIMIT_WAIT_S = 3.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_GALAXY_SEARCH_TYPE = "Person"
_RESULTS_PER_PAGE = 10

_MAX_HIGH_CONFIDENCE = 6
_MAX_OTHER_POSSIBLE = 6
_MAX_PHONES = 4
_MAX_ASSOCIATED = 6
_MAX_PREVIOUS_PER_PERSON = 8
_MAX_PREVIOUS = 12

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class EnformionTransport(Protocol):
    def post(
        self, url: str, body: dict, *, headers: dict[str, str], timeout: float
    ) -> HttpJsonResponse:
        ...


class UrllibEnformionTransport:
    """Stdlib POST-JSON transport exposing HTTP status + Retry-After."""

    def post(self, url: str, body: dict, *, headers: dict[str, str], timeout: float = _DEFAULT_TIMEOUT_S) -> HttpJsonResponse:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("User-Agent", _USER_AGENT)
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted Enformion host)
                raw = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else None
            except ValueError:
                payload = None
            return HttpJsonResponse(status=200, payload=payload)
        except urllib.error.HTTPError as exc:
            retry_after = _parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
                payload = json.loads(body_text) if body_text else None
            except (ValueError, OSError):
                payload = None
            return HttpJsonResponse(status=exc.code, payload=payload, retry_after_s=retry_after)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return HttpJsonResponse(status=0, payload=None)


def _mask(secret: str) -> str:
    if not secret:
        return ""
    return f"***{secret[-4:]}" if len(secret) > 4 else "***"


class EnformionProvider(SkipTraceProvider):
    name = "Enformion"

    def __init__(
        self,
        ap_name: str,
        ap_password: str,
        *,
        transport: Optional[EnformionTransport] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        endpoint: str = ENFORMION_PERSON_SEARCH_URL,
    ) -> None:
        self._ap_name = ap_name or ""
        self._ap_password = ap_password or ""
        self._transport = transport or UrllibEnformionTransport()
        self._sleeper = sleeper if sleeper is not None else time.sleep
        self._timeout_s = timeout_s
        self._endpoint = endpoint

    @property
    def configured(self) -> bool:
        return bool(self._ap_name and self._ap_password)

    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        line2 = ", ".join(p for p in (components.city, components.state_code) if p)
        line2 = " ".join(p for p in (line2, components.postal_code or "") if p).strip()
        body = {
            "Addresses": [{"AddressLine1": components.address_line_1 or "", "AddressLine2": line2}],
            "Includes": ["Addresses", "PhoneNumbers"],
            "FilterOptions": ["IncludeLowQualityAddresses"],
            "Page": 1,
            "ResultsPerPage": _RESULTS_PER_PAGE,
        }
        audit_params = {
            "AddressLine1": components.address_line_1 or "",
            "AddressLine2": line2,
            "ap_name": _mask(self._ap_name),
            "ap_password": _mask(self._ap_password),
        }

        if not self.configured:
            return SkipTraceResult(
                source=self.name,
                ok=False,
                audit=SkipTraceAudit(endpoint=self._endpoint, params_masked=audit_params, success=False, error="unconfigured"),
            )
        if not components.has_minimum():
            return SkipTraceResult(
                source=self.name,
                ok=False,
                audit=SkipTraceAudit(endpoint=self._endpoint, params_masked=audit_params, success=False, error="insufficient_address"),
            )

        headers = {
            "galaxy-ap-name": self._ap_name,
            "galaxy-ap-password": self._ap_password,
            "galaxy-search-type": _GALAXY_SEARCH_TYPE,
        }
        response = self._transport.post(self._endpoint, body, headers=headers, timeout=self._timeout_s)

        if response.status == 429:
            self._sleeper(min(response.retry_after_s or 1.0, _MAX_RATE_LIMIT_WAIT_S))
            response = self._transport.post(self._endpoint, body, headers=headers, timeout=self._timeout_s)
            if response.status == 429:
                return SkipTraceResult(
                    source=self.name,
                    ok=False,
                    audit=SkipTraceAudit(
                        endpoint=self._endpoint, params_masked=audit_params, http_status=429, success=False, rate_limited=True, error="rate_limited"
                    ),
                )

        if response.status != 200 or not isinstance(response.payload, dict):
            return SkipTraceResult(
                source=self.name,
                ok=False,
                audit=SkipTraceAudit(
                    endpoint=self._endpoint,
                    params_masked=audit_params,
                    http_status=response.status or None,
                    success=False,
                    error=f"http_{response.status}" if response.status else "offline",
                ),
            )

        query_number = _first_number(components.address_line_1 or "")
        query_zip = (components.postal_code or "")[:5]
        high, other, previous = _parse_persons(response.payload, query_number=query_number, query_zip=query_zip)
        return SkipTraceResult(
            source=self.name,
            ok=True,
            high_confidence=high,
            other_possible=other,
            previous_addresses=previous,
            audit=SkipTraceAudit(endpoint=self._endpoint, params_masked=audit_params, http_status=200, success=True),
        )


# --- parsing ---------------------------------------------------------------


@dataclass
class _Person:
    occupant: Occupant
    score: float
    recency: str  # date_last_seen of the matched address (sort key)


def _persons_list(payload: dict) -> list:
    for key in ("persons", "Persons", "results", "Results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _parse_persons(payload: dict, *, query_number: str, query_zip: str) -> tuple[list[Occupant], list[Occupant], list[PreviousAddress]]:
    people: list[_Person] = []
    for raw in _persons_list(payload):
        if isinstance(raw, dict):
            person = _parse_person(raw, query_number=query_number, query_zip=query_zip)
            if person is not None:
                people.append(person)
    if not people:
        return [], [], []

    # Rank by current-first, then most-recent occupancy of the matched address.
    people.sort(key=lambda p: (p.occupant.is_current, p.recency, p.score), reverse=True)
    high = people[:_MAX_HIGH_CONFIDENCE]
    other = people[_MAX_HIGH_CONFIDENCE : _MAX_HIGH_CONFIDENCE + _MAX_OTHER_POSSIBLE]

    previous: list[PreviousAddress] = []
    seen: set[str] = set()
    for person in high:
        for prev in person.occupant.previous_addresses:
            key = prev.address.lower()
            if prev.address and key not in seen:
                seen.add(key)
                previous.append(prev)
            if len(previous) >= _MAX_PREVIOUS:
                break
        if len(previous) >= _MAX_PREVIOUS:
            break

    return [p.occupant for p in high], [p.occupant for p in other], previous


def _parse_person(raw: dict, *, query_number: str, query_zip: str) -> Optional[_Person]:
    # Real API is camelCase: fullName / name{firstName,...}.
    name = str(raw.get("fullName") or "").strip() or _format_name(raw.get("name") if isinstance(raw.get("name"), dict) else {})
    if not name:
        return None

    phones: list[str] = []
    for phone in _as_list(raw.get("phoneNumbers")):
        formatted = _format_phone(phone)
        if formatted and formatted not in phones:
            phones.append(formatted)
        if len(phones) >= _MAX_PHONES:
            break

    associated: list[str] = []
    for group in ("relativesSummary", "associatesSummary"):
        for person in _as_list(raw.get(group)):
            formatted = _format_name(person if isinstance(person, dict) else {})
            if formatted and formatted not in associated:
                associated.append(formatted)
            if len(associated) >= _MAX_ASSOCIATED:
                break
        if len(associated) >= _MAX_ASSOCIATED:
            break

    # Build dated addresses, newest first.
    dated: list[tuple[str, PreviousAddress, bool]] = []  # (sort_last_seen, prev, matches_query)
    for addr in _as_list(raw.get("addresses")):
        if not isinstance(addr, dict):
            continue
        first_iso, first_disp = _parse_date(addr.get("firstReportedDate"))
        last_iso, last_disp = _parse_date(addr.get("lastReportedDate"))
        prev = PreviousAddress(
            address=_format_address(addr),
            date_first_seen=first_iso,
            date_last_seen=last_iso,
            date_range_label=_range_label(first_disp, last_disp),
        )
        matches = _address_matches(addr, query_number, query_zip)
        dated.append((last_iso or "9999", prev, matches))  # null last-seen = most recent/current
    dated.sort(key=lambda t: t[0], reverse=True)

    is_current = any(matches and last == "9999" for last, _, matches in dated)
    # If the matched address has the most-recent last-seen, treat as current too.
    if not is_current and dated and dated[0][2]:
        is_current = True
    recency = next((last for last, _, matches in dated if matches), dated[0][0] if dated else "")

    previous = [prev for _, prev, _ in dated if prev.address][:_MAX_PREVIOUS_PER_PERSON]

    try:
        score = float(raw.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    return _Person(
        occupant=Occupant(name=name, phones=phones, associated_people=associated, is_current=is_current, previous_addresses=previous),
        score=score,
        recency=recency,
    )


def _format_name(d: dict) -> str:
    if not isinstance(d, dict):
        return ""
    full = str(d.get("fullName") or "").strip()
    if full:
        return full
    parts = [str(d.get(k) or "").strip() for k in ("firstName", "middleName", "lastName", "suffix")]
    return " ".join(p for p in parts if p).strip()


def _format_phone(phone: object) -> str:
    if isinstance(phone, str):
        return phone.strip()
    if not isinstance(phone, dict):
        return ""
    number = str(phone.get("phoneNumber") or phone.get("number") or "").strip()
    if not number:
        return ""
    ptype = str(phone.get("phoneType") or phone.get("type") or "").strip()
    return f"{number} ({ptype.title()})" if ptype else number


def _format_address(addr: dict) -> str:
    full = str(addr.get("fullAddress") or "").strip()
    if full:
        return full.replace(";", ",")
    house = str(addr.get("houseNumber") or "").strip()
    pre = str(addr.get("streetPreDirection") or "").strip()
    street = str(addr.get("streetName") or "").strip()
    stype = str(addr.get("streetType") or "").strip()
    post = str(addr.get("streetPostDirection") or "").strip()
    unit = str(addr.get("unit") or "").strip()
    line1 = " ".join(p for p in (house, pre, street, stype, post) if p)
    if unit:
        line1 = f"{line1} #{unit}"
    city = str(addr.get("city") or "").strip()
    state = str(addr.get("state") or "").strip()
    zip_ = str(addr.get("zip") or "").strip()
    locality = " ".join(p for p in (", ".join(c for c in (city, state) if c), zip_) if p).strip()
    return ", ".join(p for p in (line1, locality) if p)


def _address_matches(addr: dict, query_number: str, query_zip: str) -> bool:
    if not query_number:
        return False
    house = str(addr.get("houseNumber") or "")
    if not house:
        house = _first_number(str(addr.get("fullAddress") or ""))
    if house != query_number:
        return False
    addr_zip = str(addr.get("zip") or "")[:5]
    if query_zip and addr_zip:
        return query_zip == addr_zip
    return True


def _parse_date(value: object) -> tuple[Optional[str], Optional[str]]:
    """Return (sortable ISO 'YYYY-MM-DD', display 'Mon YYYY') or (None, None)."""
    if not value or not isinstance(value, str):
        return None, None
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%Y", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        iso = dt.strftime("%Y-%m-%d")
        disp = f"{_MONTHS[dt.month]} {dt.year}" if "%m" in fmt or "/" in text else str(dt.year)
        return iso, disp
    return None, None


def _range_label(first_disp: Optional[str], last_disp: Optional[str]) -> Optional[str]:
    if not first_disp and not last_disp:
        return None
    start = first_disp or "?"
    end = last_disp or "Present"
    return f"{start} – {end}"


def _first_number(value: str) -> str:
    import re

    m = re.search(r"\d+", value or "")
    return m.group(0) if m else ""


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []
