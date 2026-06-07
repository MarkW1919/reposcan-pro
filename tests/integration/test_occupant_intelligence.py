"""Occupant intelligence: WhitePages provider parsing, cache, fallback, toggle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from reposcan_contracts.address_intel import AddressMatchQuality
from reposcan_contracts.occupant_intel import OCCUPANT_BOUNDARY_CAVEAT, OccupantLookupStatus
from reposcan_api.address_intel import AddressIntelligenceService, GeocodeResult
from reposcan_api.occupant_intel import (
    AddressComponents,
    HttpJsonResponse,
    OccupantLookupService,
    SkipTraceAudit,
    SqliteOccupantCache,
    WhitePagesProProvider,
)

# --- Example identity_check response (from the integration spec) -----------

EXAMPLE_RESPONSE = {
    "current_addresses": [
        {
            "is_primary": True,
            "address_line_1": "123 Main St",
            "city": "Oklahoma City",
            "state_code": "OK",
            "postal_code": "73102",
            "country_code": "US",
            "residents": [
                {
                    "name": "John Q. Doe",
                    "phones": [{"phone_number": "405-555-1234", "line_type": "Mobile"}],
                    "associated_people": [{"name": "Jane Doe", "relation": "Spouse"}],
                }
            ],
        }
    ],
    "previous_addresses": [
        {"address_line_1": "456 Oak Ave", "city": "Tulsa", "state_code": "OK", "postal_code": "74103"}
    ],
}


# --- Fakes -----------------------------------------------------------------


class QueueTransport:
    """Returns queued HttpJsonResponses; records the params it was called with."""

    def __init__(self, *responses: HttpJsonResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def get(self, url: str, params: dict[str, str], *, timeout: float) -> HttpJsonResponse:
        self.calls.append(dict(params))
        return self._responses.pop(0) if self._responses else HttpJsonResponse(status=0, payload=None)


@dataclass
class StubGeocoder:
    name: str = "stub_geocoder"
    matched: bool = True

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        if not self.matched:
            return GeocodeResult(matched=False, match_quality=AddressMatchQuality.none)
        return GeocodeResult(
            matched=True,
            match_quality=AddressMatchQuality.exact,
            standardized_address="123 MAIN ST, OKLAHOMA CITY, OK 73102",
            latitude=35.4676,
            longitude=-97.5164,
            county_name="Oklahoma County",
        )


def _address_service(matched: bool = True) -> AddressIntelligenceService:
    return AddressIntelligenceService(StubGeocoder(matched=matched))


def _components() -> AddressComponents:
    return AddressComponents("123 Main St", "Oklahoma City", "OK", "73102")


# --- AddressComponents.parse ----------------------------------------------


def test_parse_full_address():
    comps = AddressComponents.parse("123 Main St, Oklahoma City, OK 73102")
    assert comps.address_line_1 == "123 Main St"
    assert comps.city == "Oklahoma City"
    assert comps.state_code == "OK"
    assert comps.postal_code == "73102"


def test_parse_trims_country_and_handles_state_only():
    comps = AddressComponents.parse("742 Evergreen Terrace, Tulsa, OK, USA")
    assert comps.address_line_1 == "742 Evergreen Terrace"
    assert comps.city == "Tulsa"
    assert comps.state_code == "OK"


def test_parse_partial_is_tolerant():
    comps = AddressComponents.parse("Oklahoma City")
    assert comps.address_line_1 == "Oklahoma City"  # nothing else to infer
    assert comps.has_minimum() is False


# --- WhitePages provider parsing ------------------------------------------


def test_provider_parses_residents_phones_and_previous():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("secret-key-1234", transport=transport)
    result = provider.lookup(_components())

    assert result.ok is True
    assert result.source == "WhitePages Pro"
    assert len(result.high_confidence) == 1
    occupant = result.high_confidence[0]
    assert occupant.name == "John Q. Doe"
    assert occupant.phones == ["405-555-1234 (Mobile)"]
    assert occupant.associated_people == ["Jane Doe (Spouse)"]
    assert result.previous_addresses == ["456 Oak Ave, Tulsa, OK 74103"]


def test_provider_masks_api_key_in_audit():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("secret-key-1234", transport=transport)
    result = provider.lookup(_components())
    assert result.audit.params_masked["api_key"] == "***1234"
    # The real key is sent on the wire but never retained in the audit record.
    assert "secret-key-1234" not in str(result.audit.params_masked)
    assert transport.calls[0]["api_key"] == "secret-key-1234"


def test_provider_rate_limit_waits_then_degrades():
    waits: list[float] = []
    transport = QueueTransport(
        HttpJsonResponse(status=429, payload=None, retry_after_s=1.0),
        HttpJsonResponse(status=429, payload=None, retry_after_s=1.0),
    )
    provider = WhitePagesProProvider("k", transport=transport, sleeper=waits.append)
    result = provider.lookup(_components())
    assert result.ok is False
    assert result.audit.rate_limited is True
    assert result.audit.http_status == 429
    assert waits == [1.0]  # waited once (bounded), retried, then gave up


def test_provider_rate_limit_then_success():
    transport = QueueTransport(
        HttpJsonResponse(status=429, payload=None, retry_after_s=0.5),
        HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE),
    )
    provider = WhitePagesProProvider("k", transport=transport, sleeper=lambda _s: None)
    result = provider.lookup(_components())
    assert result.ok is True
    assert len(result.high_confidence) == 1


def test_provider_offline_returns_not_ok():
    transport = QueueTransport(HttpJsonResponse(status=0, payload=None))
    provider = WhitePagesProProvider("k", transport=transport)
    result = provider.lookup(_components())
    assert result.ok is False
    assert result.audit.success is False
    assert result.audit.error == "offline"


# --- SQLite cache ----------------------------------------------------------


def test_cache_put_get_and_age():
    cache = SqliteOccupantCache(":memory:")
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cache.put("k", {"status": "ok"}, now=now)
    entry = cache.get("k", now=now + timedelta(days=5))
    assert entry is not None
    assert entry.age_days == 5
    assert entry.is_fresh(ttl_days=30) is True
    stale = cache.get("k", now=now + timedelta(days=40))
    assert stale.is_fresh(ttl_days=30) is False


# --- Coordinator: toggle + fallback + cache --------------------------------


def test_whitepages_ok_returns_occupants_and_caches():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("k1234", transport=transport)
    cache = SqliteOccupantCache(":memory:")
    audits: list[SkipTraceAudit] = []
    svc = OccupantLookupService(_address_service(), provider=provider, cache=cache, provider_name="whitepages")

    report = svc.lookup("123 Main St, Oklahoma City, OK 73102", audit=audits.append)
    assert report.status == OccupantLookupStatus.ok
    assert report.source == "WhitePages Pro"
    assert report.high_confidence[0].name == "John Q. Doe"
    assert report.address is not None and report.address.matched is True  # census layer present
    assert OCCUPANT_BOUNDARY_CAVEAT in report.caveats
    assert len(audits) == 1 and audits[0].success is True

    # Second lookup is a fresh cache hit -> provider not called again.
    report2 = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report2.from_cache is True
    assert report2.status == OccupantLookupStatus.ok
    assert len(transport.calls) == 1


def test_whitepages_no_match_status():
    transport = QueueTransport(HttpJsonResponse(status=200, payload={"current_addresses": [], "previous_addresses": []}))
    provider = WhitePagesProProvider("k", transport=transport)
    svc = OccupantLookupService(_address_service(), provider=provider, cache=SqliteOccupantCache(":memory:"))
    report = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report.status == OccupantLookupStatus.no_match
    assert report.high_confidence == []


def test_failure_with_stale_cache_serves_offline():
    cache = SqliteOccupantCache(":memory:")
    # Seed a stale entry (fetched well beyond the TTL) directly.
    stale_at = datetime.now(timezone.utc) - timedelta(days=75)
    cache.put(
        AddressComponents.parse("123 Main St, Oklahoma City, OK 73102").cache_key(),
        {
            "status": "ok",
            "source": "WhitePages Pro",
            "high_confidence": [{"name": "John Q. Doe", "phones": [], "associated_people": []}],
            "other_possible": [],
            "previous_addresses": [],
        },
        now=stale_at,
    )

    failing = QueueTransport(HttpJsonResponse(status=0, payload=None))
    provider_fail = WhitePagesProProvider("k", transport=failing)
    svc = OccupantLookupService(_address_service(), provider=provider_fail, cache=cache, cache_ttl_days=30)

    report = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report.status == OccupantLookupStatus.offline
    assert report.from_cache is True
    assert report.cache_age_days is not None and report.cache_age_days >= 30
    assert report.high_confidence[0].name == "John Q. Doe"
    assert any("from cache" in c.lower() for c in report.caveats)


def test_failure_without_cache_is_unavailable_but_keeps_address():
    failing = QueueTransport(HttpJsonResponse(status=0, payload=None))
    provider = WhitePagesProProvider("k", transport=failing)
    svc = OccupantLookupService(_address_service(), provider=provider, cache=SqliteOccupantCache(":memory:"))
    report = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report.status == OccupantLookupStatus.unavailable
    assert report.high_confidence == []
    assert report.address is not None and report.address.matched is True  # census fallback intact


def test_config_toggle_free_mode_skips_provider():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("k", transport=transport)
    svc = OccupantLookupService(_address_service(), provider=provider, provider_name="census")
    report = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report.status == OccupantLookupStatus.disabled
    assert report.source is None
    assert report.address is not None  # free address layer still returned
    assert transport.calls == []  # paid provider never called


def test_unconfigured_when_whitepages_selected_without_provider():
    svc = OccupantLookupService(_address_service(), provider=None, provider_name="whitepages")
    report = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report.status == OccupantLookupStatus.unconfigured
    assert any("not configured" in c.lower() for c in report.caveats)
