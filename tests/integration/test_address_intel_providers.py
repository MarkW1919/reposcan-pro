"""Provider parsing tests using a stub HTTP client (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from reposcan_contracts.address_intel import AddressMatchQuality, DwellingType
from reposcan_api.address_intel import (
    AddressIntelligenceService,
    CensusGeocoderProvider,
    OverpassDwellingProvider,
)


@dataclass
class StubHttp:
    """Returns canned JSON for get_json/post_json; records calls."""

    get_payload: object = None
    post_payload: object = None
    fail: bool = False
    calls: list[str] = field(default_factory=list)

    def get_json(self, url, *, params=None, timeout=6.0):
        self.calls.append(url)
        return None if self.fail else self.get_payload

    def post_json(self, url, *, data, timeout=6.0):
        self.calls.append(url)
        return None if self.fail else self.post_payload


_CENSUS_MATCH = {
    "result": {
        "addressMatches": [
            {
                "matchedAddress": "123 MAIN ST, OKLAHOMA CITY, OK, 73101",
                "coordinates": {"x": -97.5164, "y": 35.4676},
                "geographies": {
                    "Census Blocks": [
                        {"GEOID": "401090011001000", "STATE": "40", "COUNTY": "109", "TRACT": "001100", "BLOCK": "1000"}
                    ],
                    "Counties": [{"NAME": "Oklahoma County"}],
                },
            }
        ]
    }
}


def test_census_parses_match():
    provider = CensusGeocoderProvider(StubHttp(get_payload=_CENSUS_MATCH))
    result = provider.geocode("123 Main St, Oklahoma City, OK")
    assert result is not None
    assert result.matched is True
    assert result.match_quality == AddressMatchQuality.exact
    assert result.standardized_address.startswith("123 MAIN ST")
    assert result.latitude == 35.4676 and result.longitude == -97.5164
    assert result.state_fips == "40"
    assert result.county_name == "Oklahoma County"
    assert result.block_geoid == "401090011001000"


def test_census_no_match():
    provider = CensusGeocoderProvider(StubHttp(get_payload={"result": {"addressMatches": []}}))
    result = provider.geocode("nowhere")
    assert result is not None and result.matched is False


def test_census_offline_returns_none():
    provider = CensusGeocoderProvider(StubHttp(fail=True))
    assert provider.geocode("123 Main St") is None


def test_overpass_apartments_is_multi_unit():
    payload = {"elements": [{"tags": {"building": "apartments"}}]}
    provider = OverpassDwellingProvider(StubHttp(post_payload=payload))
    result = provider.classify(35.4676, -97.5164)
    assert result.dwelling_type == DwellingType.multi_unit
    assert result.evidence == ["OSM building=apartments"]


def test_overpass_house_is_single_family():
    payload = {"elements": [{"tags": {"building": "house"}}]}
    provider = OverpassDwellingProvider(StubHttp(post_payload=payload))
    assert provider.classify(1.0, 2.0).dwelling_type == DwellingType.single_family


def test_overpass_commercial_building():
    payload = {"elements": [{"tags": {"building": "retail"}}]}
    provider = OverpassDwellingProvider(StubHttp(post_payload=payload))
    assert provider.classify(1.0, 2.0).dwelling_type == DwellingType.commercial


def test_overpass_landuse_fallback():
    payload = {"elements": [{"tags": {"building": "yes"}}, {"tags": {"landuse": "residential"}}]}
    provider = OverpassDwellingProvider(StubHttp(post_payload=payload))
    result = provider.classify(1.0, 2.0)
    assert result.dwelling_type == DwellingType.single_family
    assert "landuse=residential" in result.evidence[0]


def test_overpass_untagged_is_unknown():
    payload = {"elements": [{"tags": {"building": "yes"}}]}
    provider = OverpassDwellingProvider(StubHttp(post_payload=payload))
    assert provider.classify(1.0, 2.0).dwelling_type == DwellingType.unknown


def test_acs_parses_area_context():
    from reposcan_api.address_intel import CensusAcsAreaProvider

    # ACS returns [[header],[values]]; 410 occupied (300 owner / 110 renter),
    # 450 total units, 40 vacant.
    payload = [
        ["B25003_001E", "B25003_002E", "B25003_003E", "B25002_001E", "B25002_003E", "state", "county", "tract", "block group"],
        ["410", "300", "110", "450", "40", "40", "109", "001100", "1"],
    ]
    provider = CensusAcsAreaProvider("FAKEKEY", StubHttp(get_payload=payload))
    ctx = provider.area_context(state_fips="40", census_tract="001100", block_geoid="401090011001000")
    assert ctx is not None
    assert ctx.owner_occupied_pct == 73.2  # 300/410
    assert ctx.vacancy_pct == 8.9  # 40/450
    assert ctx.total_housing_units == 450
    assert "owner-occupied" in (ctx.summary or "")


def test_acs_requires_block_geoid():
    from reposcan_api.address_intel import CensusAcsAreaProvider

    provider = CensusAcsAreaProvider("FAKEKEY", StubHttp(get_payload=[["x"], ["1"]]))
    assert provider.area_context(state_fips="40", census_tract="001100", block_geoid=None) is None


def test_service_with_real_providers_and_stub_http_end_to_end():
    # Wire the real providers (Census + Overpass) onto a stub transport and
    # confirm the service composes a full report without any network.
    geocoder = CensusGeocoderProvider(StubHttp(get_payload=_CENSUS_MATCH))
    dwelling = OverpassDwellingProvider(StubHttp(post_payload={"elements": [{"tags": {"building": "house"}}]}))
    service = AddressIntelligenceService(geocoder, dwelling=dwelling)
    report = service.lookup("123 Main St, Oklahoma City, OK")
    assert report.matched is True
    assert report.dwelling_type == DwellingType.single_family
    assert report.county_name == "Oklahoma County"
    assert set(report.data_sources) == {"census_geocoder", "osm_overpass"}
