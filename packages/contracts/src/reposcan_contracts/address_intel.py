"""Address intelligence contract.

Given an operator-entered destination address, the address-intelligence
function aggregates ZERO-COST public/official data to help an authorized
repossession operator judge whether a debtor plausibly resides there. The
operator makes the call; this is data, not a prediction.

HONEST BOUNDARY (encoded in the report's `caveats`): free, ToS-respecting
public data establishes address existence, dwelling type, area occupancy
context, and (where a county publishes it) the owner of record. It does NOT
confirm that a specific named person lives at an address — that is gated/paid
PII (people-search / credit-header) data this system deliberately does not use.

Sources are all zero-cost and keyless-first: US Census Geocoder (keyless),
FCC Area API (keyless), OpenStreetMap/Overpass (keyless), with optional US
Census ACS area context (one free API key). No data point requires a paid
service or violates a source's terms.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class AddressMatchQuality(str, Enum):
    """How confidently the queried address resolved to a real address."""

    exact = "exact"          # standardized to a known addressable point
    approximate = "approximate"  # interpolated / street-range only
    none = "none"            # no match — address may not exist as entered


class DwellingType(str, Enum):
    """Dwelling character inferred from public map/land-use data."""

    single_family = "single_family"
    multi_unit = "multi_unit"
    commercial = "commercial"
    vacant_land = "vacant_land"
    unknown = "unknown"


class AreaContext(BaseModel):
    """Block-group-level occupancy context (US Census ACS, optional).

    Area-level ONLY — never individual. Present only when the optional ACS key
    is configured and a lookup succeeds.
    """

    owner_occupied_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    renter_occupied_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    vacancy_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    total_housing_units: Optional[int] = Field(None, ge=0)
    summary: Optional[str] = Field(None, description="Plain-language area summary")


class AddressIntelligenceReport(BaseModel):
    """Aggregated public-data report for a destination address."""

    query_address: str = Field(..., min_length=1, description="Address as the operator entered it")
    generated_at_utc: UtcTimestamp

    matched: bool = Field(False, description="Whether the address resolved to a real location")
    match_quality: AddressMatchQuality = AddressMatchQuality.none
    standardized_address: Optional[str] = Field(None, description="Normalized address from the geocoder")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

    # Census geography (FIPS) — the bridge to area context and a stable cache key.
    state_fips: Optional[str] = None
    county_name: Optional[str] = None
    census_tract: Optional[str] = None
    block_geoid: Optional[str] = None

    dwelling_type: DwellingType = DwellingType.unknown
    dwelling_evidence: list[str] = Field(
        default_factory=list,
        description="Why the dwelling type was inferred, e.g. 'OSM building=house'",
    )

    area_context: Optional[AreaContext] = None

    data_sources: list[str] = Field(
        default_factory=list, description="Providers that contributed (e.g. 'census_geocoder', 'osm_overpass')"
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Honest limitations surfaced to the operator (e.g. residency-of-a-person not establishable from free data)",
    )
    from_cache: bool = Field(False, description="True when served from the local cache (offline / repeat lookup)")


# The fixed caveat shown on every report — the residency boundary is a product
# invariant, not an incidental note.
RESIDENCY_BOUNDARY_CAVEAT = (
    "Public data shown here reflects the address and its area, not who lives there. "
    "It cannot confirm a specific person resides at this address — verify in the field."
)
