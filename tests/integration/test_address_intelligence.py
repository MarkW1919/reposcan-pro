"""Address intelligence composition + graceful degradation (stub providers)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from reposcan_contracts.address_intel import (
    RESIDENCY_BOUNDARY_CAVEAT,
    AddressMatchQuality,
    AreaContext,
    DwellingType,
)
from reposcan_api.address_intel import (
    AddressIntelligenceService,
    DwellingResult,
    GeocodeResult,
    InMemoryReportCache,
    normalize_address_key,
)


@dataclass
class StubGeocoder:
    name: str = "stub_geocoder"
    result: Optional[GeocodeResult] = None
    raises: bool = False

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        if self.raises:
            raise RuntimeError("network down")
        return self.result


@dataclass
class StubDwelling:
    name: str = "stub_dwelling"
    result: Optional[DwellingResult] = None
    raises: bool = False

    def classify(self, latitude: float, longitude: float) -> Optional[DwellingResult]:
        if self.raises:
            raise RuntimeError("overpass timeout")
        return self.result


@dataclass
class StubArea:
    name: str = "stub_area"
    result: Optional[AreaContext] = None

    def area_context(self, *, state_fips, census_tract, block_geoid) -> Optional[AreaContext]:
        return self.result


def _matched_geo() -> GeocodeResult:
    return GeocodeResult(
        matched=True,
        match_quality=AddressMatchQuality.exact,
        standardized_address="123 MAIN ST, OKLAHOMA CITY, OK 73101",
        latitude=35.4676,
        longitude=-97.5164,
        state_fips="40",
        county_name="Oklahoma County",
        census_tract="40109001100",
        block_geoid="401090011001000",
    )


def test_residency_caveat_always_present():
    svc = AddressIntelligenceService(StubGeocoder(result=_matched_geo()))
    report = svc.lookup("123 Main St")
    assert RESIDENCY_BOUNDARY_CAVEAT in report.caveats


def test_full_report_composes_all_providers():
    svc = AddressIntelligenceService(
        StubGeocoder(result=_matched_geo()),
        dwelling=StubDwelling(result=DwellingResult(DwellingType.single_family, ["OSM building=house"])),
        area=StubArea(result=AreaContext(owner_occupied_pct=72.0, renter_occupied_pct=23.0, vacancy_pct=5.0, total_housing_units=410, summary="Owner-heavy block")),
    )
    report = svc.lookup("123 Main St")
    assert report.matched is True
    assert report.match_quality == AddressMatchQuality.exact
    assert report.standardized_address.startswith("123 MAIN ST")
    assert report.dwelling_type == DwellingType.single_family
    assert report.dwelling_evidence == ["OSM building=house"]
    assert report.area_context.owner_occupied_pct == 72.0
    assert set(report.data_sources) == {"stub_geocoder", "stub_dwelling", "stub_area"}


def test_unmatched_address_degrades_cleanly():
    svc = AddressIntelligenceService(StubGeocoder(result=GeocodeResult(matched=False, match_quality=AddressMatchQuality.none)))
    report = svc.lookup("nowhere at all")
    assert report.matched is False
    assert report.dwelling_type == DwellingType.unknown
    assert any("could not be resolved" in c for c in report.caveats)


def test_geocoder_offline_does_not_raise():
    # A provider that raises must degrade to an unmatched report, not blow up.
    svc = AddressIntelligenceService(StubGeocoder(raises=True))
    report = svc.lookup("123 Main St")
    assert report.matched is False
    assert any("offline" in c.lower() for c in report.caveats)


def test_dwelling_provider_failure_keeps_partial_report():
    svc = AddressIntelligenceService(
        StubGeocoder(result=_matched_geo()),
        dwelling=StubDwelling(raises=True),
    )
    report = svc.lookup("123 Main St")
    assert report.matched is True  # geocode succeeded
    assert report.dwelling_type == DwellingType.unknown
    assert any("Dwelling type" in c for c in report.caveats)
    assert "stub_dwelling" not in report.data_sources


def test_cache_hit_sets_from_cache_and_skips_providers():
    cache = InMemoryReportCache()
    geocoder = StubGeocoder(result=_matched_geo())
    svc = AddressIntelligenceService(geocoder, cache=cache)

    first = svc.lookup("123 Main St")
    assert first.from_cache is False
    # Swap the geocoder to one that would raise — a cache hit must not call it.
    svc._geocoder = StubGeocoder(raises=True)  # type: ignore[attr-defined]
    second = svc.lookup("123 MAIN st")  # different case -> same normalized key
    assert second.from_cache is True
    assert second.matched is True


def test_unmatched_report_not_cached():
    cache = InMemoryReportCache()
    svc = AddressIntelligenceService(StubGeocoder(result=GeocodeResult(matched=False, match_quality=AddressMatchQuality.none)), cache=cache)
    svc.lookup("nowhere")
    assert cache.get(normalize_address_key("nowhere")) is None
