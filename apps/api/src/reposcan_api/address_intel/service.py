"""Address intelligence composition service.

Orchestrates a geocoder (required), and optional dwelling + area providers,
into an AddressIntelligenceReport. Pure orchestration + graceful degradation —
no network code here; concrete HTTP providers are injected. Safe to call
offline: a None geocode yields an unmatched report rather than an error, and
cached reports serve repeat/offline lookups.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from reposcan_contracts.address_intel import (
    RESIDENCY_BOUNDARY_CAVEAT,
    AddressIntelligenceReport,
    AddressMatchQuality,
    DwellingType,
)

from .providers import AreaProvider, DwellingProvider, GeocodeProvider, ReportCache


def normalize_address_key(address: str) -> str:
    """Stable cache key for an address query (case/space-insensitive)."""
    return " ".join(address.strip().lower().split())


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InMemoryReportCache:
    """Process-local report cache (repeat lookups + short-term offline reuse)."""

    def __init__(self) -> None:
        self._store: dict[str, AddressIntelligenceReport] = {}

    def get(self, key: str) -> Optional[AddressIntelligenceReport]:
        return self._store.get(key)

    def put(self, key: str, report: object) -> None:
        if isinstance(report, AddressIntelligenceReport):
            self._store[key] = report


class AddressIntelligenceService:
    def __init__(
        self,
        geocoder: GeocodeProvider,
        *,
        dwelling: Optional[DwellingProvider] = None,
        area: Optional[AreaProvider] = None,
        cache: Optional[ReportCache] = None,
        clock: Callable[[], str] = _utcnow,
    ) -> None:
        self._geocoder = geocoder
        self._dwelling = dwelling
        self._area = area
        self._cache = cache
        self._clock = clock

    def lookup(
        self,
        address: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> AddressIntelligenceReport:
        # Coords (when the UI has already resolved/staged a destination) make
        # the key unique so a coord-backed result doesn't collide with a raw
        # string lookup of the same text.
        key = normalize_address_key(address)
        if latitude is not None and longitude is not None:
            key = f"{key}@{latitude:.5f},{longitude:.5f}"
        if self._cache is not None:
            cached = self._cache.get(key)
            if isinstance(cached, AddressIntelligenceReport):
                return cached.model_copy(update={"from_cache": True})

        report = self._build(address, latitude, longitude)

        # Only cache resolved reports — an offline/unmatched miss should be
        # retried later, not pinned in the cache.
        if self._cache is not None and report.matched:
            self._cache.put(key, report)
        return report

    def _build(self, address: str, latitude: float | None, longitude: float | None) -> AddressIntelligenceReport:
        sources: list[str] = []
        caveats: list[str] = [RESIDENCY_BOUNDARY_CAVEAT]

        geo = _safe(lambda: self._geocoder.geocode(address))
        if geo is not None and geo.matched:
            sources.append(self._geocoder.name)
        elif latitude is not None and longitude is not None:
            # Forward geocoding the typed text failed (vague/partial/format),
            # but the UI already resolved coordinates for this destination —
            # reverse-geocode from them so a staged destination always resolves.
            reverse = getattr(self._geocoder, "reverse_geocode", None)
            geo_rev = _safe(lambda: reverse(latitude, longitude)) if callable(reverse) else None
            if geo_rev is not None and geo_rev.matched:
                geo = geo_rev
                if geo.standardized_address is None:
                    geo.standardized_address = address
                sources.append(self._geocoder.name)

        if geo is None or not geo.matched:
            caveats.append(
                "Address could not be resolved against public records "
                "(it may be mistyped, brand-new, or address lookup is offline)."
            )
            return AddressIntelligenceReport(
                query_address=address,
                generated_at_utc=self._clock(),
                matched=False,
                match_quality=AddressMatchQuality.none,
                data_sources=sources,
                caveats=caveats,
            )

        dwelling_type = DwellingType.unknown
        dwelling_evidence: list[str] = []
        if self._dwelling is not None and geo.latitude is not None and geo.longitude is not None:
            dwelling = _safe(lambda: self._dwelling.classify(geo.latitude, geo.longitude))
            if dwelling is not None:
                dwelling_type = dwelling.dwelling_type
                dwelling_evidence = dwelling.evidence
                sources.append(self._dwelling.name)

        area_context = None
        if self._area is not None:
            area_context = _safe(
                lambda: self._area.area_context(
                    state_fips=geo.state_fips,
                    census_tract=geo.census_tract,
                    block_geoid=geo.block_geoid,
                )
            )
            if area_context is not None:
                sources.append(self._area.name)

        if dwelling_type == DwellingType.unknown:
            caveats.append("Dwelling type could not be determined from available map data.")

        return AddressIntelligenceReport(
            query_address=address,
            generated_at_utc=self._clock(),
            matched=True,
            match_quality=geo.match_quality,
            standardized_address=geo.standardized_address,
            latitude=geo.latitude,
            longitude=geo.longitude,
            state_fips=geo.state_fips,
            county_name=geo.county_name,
            census_tract=geo.census_tract,
            block_geoid=geo.block_geoid,
            dwelling_type=dwelling_type,
            dwelling_evidence=dwelling_evidence,
            area_context=area_context,
            data_sources=sources,
            caveats=caveats,
        )


def _safe(call: Callable):
    """Run a provider call, swallowing expected failures to None.

    Providers are contractually best-effort; a network error or unexpected
    payload must degrade the report, not raise.
    """
    try:
        return call()
    except Exception:
        return None
