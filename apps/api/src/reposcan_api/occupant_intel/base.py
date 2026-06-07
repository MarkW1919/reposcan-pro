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
_TRAILING_ZIP_RE = re.compile(r"(\d{5}(?:-\d{4})?)\s*$")
_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
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

        Tolerant by design — a partial parse still lets a provider try, and the
        provider/coordinator degrades if the match is poor. Handles the common
        "123 Main St, Oklahoma City, OK 73102" shape and trims a trailing
        "USA"/"United States".
        """
        cleaned = address.strip()
        if not cleaned:
            return cls()
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        # Drop a trailing country token so it doesn't get parsed as state/zip.
        if parts and parts[-1].lower() in {"usa", "us", "united states", "united states of america"}:
            parts = parts[:-1]
        if not parts:
            return cls()

        address_line_1: Optional[str] = parts[0] or None
        city: Optional[str] = None
        state_code: Optional[str] = None
        postal_code: Optional[str] = None

        # Parse the last segment for "ST 12345" / "12345" / "State".
        last = parts[-1] if len(parts) > 1 else ""
        state_zip = _STATE_ZIP_RE.match(last)
        if state_zip:
            state_code = state_zip.group(1).upper()
            postal_code = state_zip.group(2)
            remaining = parts[1:-1]
        else:
            zip_match = _TRAILING_ZIP_RE.search(last)
            if zip_match:
                postal_code = zip_match.group(1)
                token = last[: zip_match.start()].strip().rstrip(",").strip()
                if token.upper() in _STATE_CODES:
                    state_code = token.upper()
                    remaining = parts[1:-1]
                elif token:
                    # last segment was "City 12345" (no state)
                    city = token
                    remaining = parts[1:-1]
                else:
                    remaining = parts[1:-1]
            elif last.upper() in _STATE_CODES:
                state_code = last.upper()
                remaining = parts[1:-1]
            else:
                remaining = parts[1:]

        if city is None and remaining:
            city = remaining[-1] or None

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
