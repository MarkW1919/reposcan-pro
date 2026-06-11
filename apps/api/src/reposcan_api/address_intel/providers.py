"""Provider protocols + result types for address intelligence.

Providers are intentionally narrow and independently optional so the service
can compose whatever is available and degrade gracefully. Each provider is
best-effort: it returns None on failure/offline rather than raising, so a
single unavailable source never breaks the whole report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from reposcan_contracts.address_intel import AddressMatchQuality, AreaContext, DwellingType


@dataclass
class GeocodeResult:
    """Normalized output of a geocoding provider."""

    matched: bool
    match_quality: AddressMatchQuality
    standardized_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    state_fips: Optional[str] = None
    county_name: Optional[str] = None
    census_tract: Optional[str] = None
    block_geoid: Optional[str] = None


@dataclass
class DwellingResult:
    """Dwelling characterization from map/land-use data."""

    dwelling_type: DwellingType
    evidence: list[str] = field(default_factory=list)


@runtime_checkable
class GeocodeProvider(Protocol):
    name: str

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        """Resolve an address to a standardized address + coordinates + FIPS.

        Returns None on failure/offline (never raises for expected failures).
        """
        ...


@runtime_checkable
class DwellingProvider(Protocol):
    name: str

    def classify(self, latitude: float, longitude: float) -> Optional[DwellingResult]:
        """Infer dwelling type at a coordinate. None on failure/offline."""
        ...


@runtime_checkable
class AreaProvider(Protocol):
    name: str

    def area_context(
        self,
        *,
        state_fips: Optional[str],
        census_tract: Optional[str],
        block_geoid: Optional[str],
    ) -> Optional[AreaContext]:
        """Block-group area occupancy context. None when unavailable/unconfigured."""
        ...


@runtime_checkable
class ReportCache(Protocol):
    def get(self, key: str) -> Optional[object]:
        ...

    def put(self, key: str, report: object) -> None:
        ...
