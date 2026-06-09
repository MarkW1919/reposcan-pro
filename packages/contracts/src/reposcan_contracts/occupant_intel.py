"""Occupant intelligence contract.

For an operator-staged destination, occupant intelligence answers "who is
associated with this address" using a licensed, paid skip-trace provider
(WhitePages Pro), with automatic fallback to the free Census/OSM address
verification when the paid provider is unavailable.

LAWFUL-USE NOTE: occupant/skip-trace data (names, phones, associates, prior
addresses) is regulated (FCRA/GLBA/DPPA and state law). This module is for an
authorized, attorney-reviewed repossession workflow only. Every lookup is
audited; the API key is never logged or returned. The embedded address
verification (``address``) is the always-available, zero-cost base layer.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from .address_intel import AddressIntelligenceReport
from .types import UtcTimestamp


class PreviousAddress(BaseModel):
    """A prior address for a person, with an optional residency date range.

    Dates come from a dates-capable provider (e.g. Enformion FirstReportedDate /
    LastReportedDate); providers without dates (e.g. WhitePages) leave them None.
    """

    address: str = Field(..., min_length=1)
    date_first_seen: Optional[str] = Field(
        None, description="When the person first appeared at this address (ISO date or YYYY-MM)."
    )
    date_last_seen: Optional[str] = Field(
        None, description="When last seen here (ISO date or YYYY-MM); None can mean still current/unknown."
    )
    date_range_label: Optional[str] = Field(
        None, description='Human-readable range, e.g. "2015 – Present" or "2012 – 2018".'
    )


def _coerce_previous_addresses(value: Any) -> Any:
    """Accept legacy list[str] (older cache payloads) and bare strings."""
    if isinstance(value, list):
        return [{"address": item} if isinstance(item, str) else item for item in value]
    return value


class OccupantLookupStatus(str, Enum):
    ok = "ok"                    # provider returned occupant data
    no_match = "no_match"        # provider ran, found no occupants
    unavailable = "unavailable"  # provider errored/timed out -> fell back
    offline = "offline"          # served stale cache while offline
    disabled = "disabled"        # occupant provider intentionally off (free mode)
    unconfigured = "unconfigured"  # no API key configured


class Occupant(BaseModel):
    """A person associated with the address (UI-ready, pre-formatted)."""

    name: str = Field(..., min_length=1)
    phones: list[str] = Field(default_factory=list, description='e.g. "405-555-1234 (Mobile)"')
    associated_people: list[str] = Field(default_factory=list, description='e.g. "Jane Doe (Spouse)"')
    is_current: bool = Field(
        default=False,
        description="True when the searched address is in this person's current addresses (current resident) vs historic only.",
    )
    previous_addresses: list[PreviousAddress] = Field(
        default_factory=list,
        description="This person's own prior addresses (most recent first), with date ranges when available.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, data: Any) -> Any:
        # Tolerate cached payloads written before previous_addresses was structured.
        if isinstance(data, dict) and "previous_addresses" in data:
            data = {**data, "previous_addresses": _coerce_previous_addresses(data["previous_addresses"])}
        return data


class OccupantIntelligenceReport(BaseModel):
    """Combined occupant + address report for a staged destination."""

    lookup_address: str = Field(..., min_length=1)
    generated_at_utc: UtcTimestamp

    status: OccupantLookupStatus = OccupantLookupStatus.disabled
    source: Optional[str] = Field(None, description="Occupant data source, e.g. 'WhitePages Pro'")
    high_confidence: list[Occupant] = Field(default_factory=list)
    other_possible: list[Occupant] = Field(default_factory=list)
    previous_addresses: list[PreviousAddress] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_report(cls, data: Any) -> Any:
        if isinstance(data, dict) and "previous_addresses" in data:
            data = {**data, "previous_addresses": _coerce_previous_addresses(data["previous_addresses"])}
        return data

    from_cache: bool = False
    cache_age_days: Optional[int] = Field(None, ge=0, description="Age of cached occupant data when served from cache")

    # Always-available base/fallback layer: Census/OSM address verification.
    address: Optional[AddressIntelligenceReport] = None

    caveats: list[str] = Field(default_factory=list)


# Occupant identity is corroborative, not proof of current residence — surfaced
# on every report so the operator verifies in the field.
OCCUPANT_BOUNDARY_CAVEAT = (
    "Occupant data is third-party record data and may be outdated or incorrect. "
    "It indicates people historically associated with this address, not proof of "
    "who currently lives there — confirm in the field before acting."
)
