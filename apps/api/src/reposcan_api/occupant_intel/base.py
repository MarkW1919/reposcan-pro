"""Skip-trace provider abstraction + shared value types.

A skip-trace provider takes structured US address components and returns the
people associated with that address. Providers are best-effort: they never
raise for an expected failure (network/HTTP/parse/rate-limit) — instead they
return a SkipTraceResult whose ``audit`` records what happened, so the
coordinator can fall back and the audit trail is complete.

LAWFUL-USE: see reposcan_contracts.occupant_intel. The API key is never stored
on these objects' public surface, never logged, and masked in audit params.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from reposcan_contracts.occupant_intel import Occupant

_STATE_ZIP_RE = re.compile(r"^\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)\s*$")
_FULL_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
_UNIT_RE = re.compile(r"^(apt|apartment|suite|ste|unit|bldg|building|fl|floor|rm|room|#)\b.*$", re.IGNORECASE)
_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
_COUNTRY_TOKENS = {"usa", "us", "united states", "united states of america"}
_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC",
}


@dataclass(frozen=True)
class AddressComponents:
    """Structured address inputs for a skip-trace lookup."""

    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state_code: Optional[str] = None
    postal_code: Optional[str] = None

    def display(self) -> str:
        """Single-line address for ``lookup_address`` / display."""
        city_state = ", ".join(p for p in (self.city, self.state_code) if p)
        locality = " ".join(p for p in (city_state, self.postal_code) if p).strip()
        return ", ".join(p for p in (self.address_line_1, locality) if p)

    def cache_key(self) -> str:
        """Stable, case/space-insensitive cache key."""
        raw = "|".join(
            (self.address_line_1 or "", self.city or "", self.state_code or "", self.postal_code or "")
        )
        return " ".join(raw.lower().split())

    def has_minimum(self) -> bool:
        """Enough to attempt a lookup (street line + some locality signal)."""
        return bool(self.address_line_1 and (self.city or self.state_code or self.postal_code))

    @classmethod
    def parse(cls, address: str) -> "AddressComponents":
        """Best-effort split of a free-form US address string into components.

        Order-tolerant: handles both the clean form
        "123 Main St, Oklahoma City, OK 73102" and the verbose map/Nominatim form
        "411, Sherrard Street, Colbert, Bryan County, Oklahoma, 74733, United
        States" (house number split from the street, full state names, a "<X>
        County" token, and a country suffix).
        """
        cleaned = address.strip()
        if not cleaned:
            return cls()
        tokens = [p.strip() for p in cleaned.split(",") if p.strip()]

        state_code: Optional[str] = None
        postal_code: Optional[str] = None
        kept: list[str] = []
        # Pass 1: unambiguous tokens (country, zip, "ST ZIP", 2-letter state,
        # county). Full state NAMES are deferred — "Washington" is also a city,
        # so an explicit code like "DC" must win first.
        for token in tokens:
            low = token.lower()
            if low in _COUNTRY_TOKENS:
                continue
            state_zip = _STATE_ZIP_RE.match(token)  # "OK 73102"
            if state_zip:
                state_code = state_code or state_zip.group(1).upper()
                postal_code = postal_code or state_zip.group(2)
                continue
            if _FULL_ZIP_RE.match(token):  # "73102"
                postal_code = postal_code or token
                continue
            if low.endswith(" county"):  # drop county descriptor
                continue
            if state_code is None and token.upper() in _STATE_CODES:
                state_code = token.upper()
                continue
            kept.append(token)

        address_line_1: Optional[str] = None
        city: Optional[str] = None
        if kept:
            # Verbose form splits the house number into its own token ("411",
            # "Sherrard Street"); rejoin it with the street. Clean form keeps the
            # whole street line in one token ("123 Main St").
            if kept[0].isdigit() and len(kept) >= 2:
                address_line_1 = f"{kept[0]} {kept[1]}"
                rest = kept[2:]
            else:
                address_line_1 = kept[0]
                rest = kept[1:]
            # A unit/suite token (its own comma segment) belongs on the street
            # line for the provider, not silently dropped as if it were a city.
            if rest and _UNIT_RE.match(rest[0]):
                address_line_1 = f"{address_line_1}, {rest[0]}"
                rest = rest[1:]
            # A trailing full state NAME (no explicit 2-letter code seen) — e.g.
            # "..., Colbert, Oklahoma" — resolves to the state, but only if a city
            # still remains. "123 Main St, New York" keeps New York as the city.
            if state_code is None and len(rest) >= 2 and rest[-1].lower() in _STATE_NAMES:
                state_code = _STATE_NAMES[rest[-1].lower()]
                rest = rest[:-1]
            city = rest[-1] if rest else None

        return cls(
            address_line_1=address_line_1,
            city=city,
            state_code=state_code,
            postal_code=postal_code,
        )


@dataclass
class SkipTraceAudit:
    """What a single provider call did, for the audit trail (no secrets)."""

    endpoint: str
    params_masked: dict[str, str]
    http_status: Optional[int] = None
    success: bool = False
    rate_limited: bool = False
    error: Optional[str] = None


@dataclass
class SkipTraceResult:
    """Normalized provider output + the audit record for the call."""

    source: str
    audit: SkipTraceAudit
    high_confidence: list[Occupant] = field(default_factory=list)
    other_possible: list[Occupant] = field(default_factory=list)
    previous_addresses: list[str] = field(default_factory=list)
    ok: bool = False  # the call completed and returned parseable data

    @property
    def has_occupants(self) -> bool:
        return bool(self.high_confidence or self.other_possible)


class SkipTraceProvider(ABC):
    """Abstract base for occupant/skip-trace providers."""

    name: str = "skip_trace"

    @abstractmethod
    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        """Resolve occupants for an address. Never raises for expected failures."""
        raise NotImplementedError
