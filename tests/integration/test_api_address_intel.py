"""API endpoint test for /address-intelligence (stub provider, no network)."""

from __future__ import annotations

from typing import Optional

from fastapi.testclient import TestClient

from reposcan_api import create_app
from reposcan_api.address_intel import AddressIntelligenceService, GeocodeResult
from reposcan_contracts.address_intel import AddressMatchQuality
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService


class _StubGeocoder:
    name = "census_geocoder"

    def __init__(self, result: Optional[GeocodeResult]) -> None:
        self._result = result

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        return self._result


def _client(tmp_path, geocode_result: Optional[GeocodeResult]) -> TestClient:
    storage = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
    intel = AddressIntelligenceService(_StubGeocoder(geocode_result))
    return TestClient(create_app(storage_service=storage, address_intel_service=intel))


def test_address_intelligence_endpoint_matched(tmp_path):
    result = GeocodeResult(
        matched=True,
        match_quality=AddressMatchQuality.exact,
        standardized_address="123 MAIN ST, OKLAHOMA CITY, OK, 73101",
        latitude=35.4676,
        longitude=-97.5164,
        county_name="Oklahoma County",
        block_geoid="401090011001000",
    )
    client = _client(tmp_path, result)
    resp = client.get("/address-intelligence", params={"address": "123 Main St, Oklahoma City, OK"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["standardized_address"].startswith("123 MAIN ST")
    assert body["county_name"] == "Oklahoma County"
    assert body["data_sources"] == ["census_geocoder"]
    # The residency boundary caveat is always present.
    assert any("verify in the field" in c.lower() for c in body["caveats"])


def test_address_intelligence_endpoint_unmatched(tmp_path):
    client = _client(tmp_path, GeocodeResult(matched=False, match_quality=AddressMatchQuality.none))
    resp = client.get("/address-intelligence", params={"address": "nowhere road"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is False
    assert body["dwelling_type"] == "unknown"


def test_address_intelligence_requires_min_length(tmp_path):
    client = _client(tmp_path, None)
    resp = client.get("/address-intelligence", params={"address": "ab"})
    assert resp.status_code == 422  # below min_length
