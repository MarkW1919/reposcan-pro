"""API endpoint test for /occupant-intelligence (injected service, no network)."""

from __future__ import annotations

from typing import Optional

from fastapi.testclient import TestClient

from reposcan_api import create_app
from reposcan_api.address_intel import AddressIntelligenceService, GeocodeResult
from reposcan_api.occupant_intel import (
    HttpJsonResponse,
    OccupantLookupService,
    SqliteOccupantCache,
    WhitePagesProProvider,
)
from reposcan_contracts.address_intel import AddressMatchQuality
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService

EXAMPLE_RESPONSE = {
    "results": [
        {
            "id": "p1",
            "name": "John Q. Doe",
            "phones": [{"number": "405-555-1234", "type": "mobile", "score": 4}],
            "relatives": [{"id": "r1", "name": "Jane Doe"}],
            "current_addresses": [
                {"address_id": "a1", "full_address": "123 Main St, Oklahoma City, OK 73102", "line1": "123 Main St", "city": "Oklahoma City", "state": "OK", "zip": "73102"}
            ],
            "historic_addresses": [
                {"address_id": "a2", "full_address": "456 Oak Ave, Tulsa, OK 74103", "line1": "456 Oak Ave", "city": "Tulsa", "state": "OK", "zip": "74103"}
            ],
            "match_score": 100,
            "matched_by": ["address"],
            "emails": [],
        }
    ],
    "metadata": {"result_count": 1, "page": 1, "page_size": 15},
}


class _StubGeocoder:
    name = "census_geocoder"

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        return GeocodeResult(
            matched=True,
            match_quality=AddressMatchQuality.exact,
            standardized_address="123 MAIN ST, OKLAHOMA CITY, OK 73102",
            latitude=35.4676,
            longitude=-97.5164,
            county_name="Oklahoma County",
        )


class _QueueTransport:
    def __init__(self, *responses: HttpJsonResponse) -> None:
        self._responses = list(responses)

    def get(self, url, params, *, headers=None, timeout):  # noqa: ANN001
        return self._responses.pop(0) if self._responses else HttpJsonResponse(status=0, payload=None)


def _client(tmp_path, *, provider_name="whitepages", transport=None) -> TestClient:
    storage = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
    address_intel = AddressIntelligenceService(_StubGeocoder())
    provider = None
    if provider_name == "whitepages":
        provider = WhitePagesProProvider(
            "secret-1234",
            transport=transport or _QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE)),
        )
    occupant = OccupantLookupService(
        address_intel,
        provider=provider,
        provider_name=provider_name,
        cache=SqliteOccupantCache(":memory:"),
    )
    return TestClient(create_app(storage_service=storage, address_intel_service=address_intel, occupant_intel_service=occupant))


def test_occupant_endpoint_returns_occupants(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/occupant-intelligence", params={"address": "123 Main St, Oklahoma City, OK 73102"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["source"] == "WhitePages Pro"
    assert body["high_confidence"][0]["name"] == "John Q. Doe"
    assert body["high_confidence"][0]["phones"] == ["405-555-1234 (Mobile)"]
    assert body["high_confidence"][0]["associated_people"] == ["Jane Doe"]
    assert body["previous_addresses"] == ["456 Oak Ave, Tulsa, OK 74103"]
    # Census address layer is embedded as the base/fallback.
    assert body["address"]["matched"] is True
    assert body["address"]["county_name"] == "Oklahoma County"


def test_occupant_endpoint_free_mode_disables_provider(tmp_path):
    client = _client(tmp_path, provider_name="census")
    resp = client.get("/occupant-intelligence", params={"address": "123 Main St, Oklahoma City, OK 73102"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "disabled"
    assert body["source"] is None
    assert body["address"]["matched"] is True  # free layer still returned


def test_occupant_endpoint_offline_degrades_not_5xx(tmp_path):
    client = _client(tmp_path, transport=_QueueTransport(HttpJsonResponse(status=0, payload=None)))
    resp = client.get("/occupant-intelligence", params={"address": "123 Main St, Oklahoma City, OK 73102"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["address"]["matched"] is True


def test_occupant_endpoint_requires_min_length(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/occupant-intelligence", params={"address": "ab"})
    assert resp.status_code == 422
