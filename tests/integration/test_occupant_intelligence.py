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
    "results": [
        {
            "id": "p1",
            "name": "John Q. Doe",
            "aliases": [],
            "is_dead": False,
            "owned_properties": [],
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
        },
        {
            "id": "p2",
            "name": "Bob Roe",
            "aliases": [],
            "is_dead": False,
            "owned_properties": [],
            "phones": [{"number": "405-555-9999", "type": "Landline", "score": 2}],
            "relatives": [],
            "current_addresses": [
                {"address_id": "a1", "full_address": "123 Main St, Oklahoma City, OK 73102", "line1": "123 Main St", "city": "Oklahoma City", "state": "OK", "zip": "73102"}
            ],
            "historic_addresses": [],
            "match_score": 40,
            "matched_by": ["address"],
            "emails": [],
        },
    ],
    "metadata": {"result_count": 2, "page": 1, "page_size": 15},
}


# --- Fakes -----------------------------------------------------------------


class QueueTransport:
    """Returns queued HttpJsonResponses; records params + headers per call."""

    def __init__(self, *responses: HttpJsonResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []
        self.headers: list[dict[str, str]] = []

    def get(self, url, params, *, headers=None, timeout):  # noqa: ANN001
        self.calls.append(dict(params))
        self.headers.append(dict(headers or {}))
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


def test_parse_verbose_nominatim_label():
    # The exact verbose label the map suggestions produce.
    comps = AddressComponents.parse("411, Sherrard Street, Colbert, Bryan County, Oklahoma, 74733, United States")
    assert comps.address_line_1 == "411 Sherrard Street"  # house # rejoined to street
    assert comps.city == "Colbert"  # county token dropped, not used as city
    assert comps.state_code == "OK"  # full state name resolved
    assert comps.postal_code == "74733"
    assert comps.has_minimum() is True


def test_parse_city_named_like_a_state_keeps_explicit_state():
    # "Washington" is a city here; the explicit "DC" must win as the state.
    comps = AddressComponents.parse("1600 Pennsylvania Ave NW, Washington, DC 20500")
    assert comps.address_line_1 == "1600 Pennsylvania Ave NW"
    assert comps.city == "Washington"
    assert comps.state_code == "DC"
    assert comps.postal_code == "20500"


# --- WhitePages provider parsing ------------------------------------------


def test_provider_parses_residents_phones_and_previous():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("secret-key-1234", transport=transport)
    result = provider.lookup(_components())

    assert result.ok is True
    assert result.source == "WhitePages Pro"
    # match_score split: John (100) is high confidence, Bob (40) is a maybe.
    assert len(result.high_confidence) == 1
    occupant = result.high_confidence[0]
    assert occupant.name == "John Q. Doe"
    assert occupant.phones == ["405-555-1234 (Mobile)"]
    assert occupant.associated_people == ["Jane Doe"]
    # Searched address is in John's current_addresses -> current resident, and
    # his own prior addresses ride on the occupant (not a global pile).
    assert occupant.is_current is True
    assert [p.address for p in occupant.previous_addresses] == ["456 Oak Ave, Tulsa, OK 74103"]
    # WhitePages has no dates -> date fields are None (Enformion fills them).
    assert occupant.previous_addresses[0].date_range_label is None
    assert len(result.other_possible) == 1
    assert result.other_possible[0].name == "Bob Roe"
    # Report-level previous still aggregates the strong matches' history.
    assert [p.address for p in result.previous_addresses] == ["456 Oak Ave, Tulsa, OK 74103"]
    # Request used the documented address params (not postal_code) + history flag.
    assert transport.calls[0]["zipcode"] == "73102"
    assert transport.calls[0]["include_historical_locations"] == "true"
    assert "postal_code" not in transport.calls[0]


def test_provider_masks_api_key_in_audit():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("secret-key-1234", transport=transport)
    result = provider.lookup(_components())
    assert result.audit.params_masked["api_key"] == "***1234"
    # The real key travels in the X-Api-Key header, never in query params or audit.
    assert "secret-key-1234" not in str(result.audit.params_masked)
    assert "api_key" not in transport.calls[0]
    assert transport.headers[0]["X-Api-Key"] == "secret-key-1234"


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
    transport = QueueTransport(HttpJsonResponse(status=200, payload={"results": [], "metadata": {"result_count": 0}}))
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


# --- Hardening: parsing edge cases ----------------------------------------


def test_parse_keeps_unit_suite_on_street_line():
    comps = AddressComponents.parse("123 Main St, Suite 200, Dallas, TX 75201")
    assert comps.address_line_1 == "123 Main St, Suite 200"  # not silently dropped
    assert comps.city == "Dallas"
    assert comps.state_code == "TX"
    assert comps.postal_code == "75201"


def test_parse_city_named_like_a_state_with_zip_stays_city():
    # "New York" here is the city (no explicit state); the ZIP shouldn't let the
    # parser steal the only locality token as a state.
    comps = AddressComponents.parse("123 Main St, New York, 10001")
    assert comps.address_line_1 == "123 Main St"
    assert comps.city == "New York"
    assert comps.postal_code == "10001"


def test_parse_po_box():
    comps = AddressComponents.parse("PO Box 1234, Tulsa, OK 74103")
    assert comps.address_line_1 == "PO Box 1234"
    assert comps.city == "Tulsa"
    assert comps.state_code == "OK"


# --- Hardening: provider robustness ---------------------------------------


def test_provider_skips_call_without_minimum_address():
    transport = QueueTransport(HttpJsonResponse(status=200, payload=EXAMPLE_RESPONSE))
    provider = WhitePagesProProvider("k", transport=transport)
    result = provider.lookup(AddressComponents(city="Tulsa"))  # no street -> insufficient
    assert result.ok is False
    assert result.audit.error == "insufficient_address"
    assert transport.calls == []  # no paid call attempted


def test_provider_non_dict_200_degrades():
    transport = QueueTransport(HttpJsonResponse(status=200, payload="<html>maintenance</html>"))
    provider = WhitePagesProProvider("k", transport=transport)
    result = provider.lookup(_components())
    assert result.ok is False


def test_all_zero_scores_go_to_other_possible():
    payload = {
        "results": [
            {"id": "p1", "name": "A B", "phones": [], "relatives": [], "current_addresses": [], "historic_addresses": [], "match_score": 0},
            {"id": "p2", "name": "C D", "phones": [], "relatives": [], "current_addresses": [], "historic_addresses": [], "match_score": 0},
        ],
        "metadata": {"result_count": 2},
    }
    provider = WhitePagesProProvider("k", transport=QueueTransport(HttpJsonResponse(status=200, payload=payload)))
    result = provider.lookup(_components())
    assert result.ok is True
    assert result.high_confidence == []  # nobody over-promoted when all scores are 0
    assert len(result.other_possible) == 2


# --- Hardening: cache behavior --------------------------------------------


def test_no_match_is_not_cached():
    empty = {"results": [], "metadata": {"result_count": 0}}
    transport = QueueTransport(
        HttpJsonResponse(status=200, payload=empty),
        HttpJsonResponse(status=200, payload=empty),
    )
    provider = WhitePagesProProvider("k", transport=transport)
    svc = OccupantLookupService(_address_service(), provider=provider, cache=SqliteOccupantCache(":memory:"))
    r1 = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    r2 = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert r1.status == OccupantLookupStatus.no_match
    assert r2.status == OccupantLookupStatus.no_match
    assert len(transport.calls) == 2  # not served from cache -> re-queried


def test_cache_purge_expired_drops_old_keeps_fresh():
    cache = SqliteOccupantCache(":memory:")
    now = datetime.now(timezone.utc)
    cache.put("old", {"status": "ok"}, now=now - timedelta(days=40))
    cache.put("fresh", {"status": "ok"}, now=now - timedelta(days=2))
    removed = cache.purge_expired(ttl_days=30, now=now)
    assert removed == 1
    assert cache.get("old") is None
    assert cache.get("fresh") is not None


def test_cached_payload_tolerates_extra_fields():
    cache = SqliteOccupantCache(":memory:")
    cache.put(
        AddressComponents.parse("123 Main St, Oklahoma City, OK 73102").cache_key(),
        {
            "status": "ok",
            "source": "WhitePages Pro",
            "high_confidence": [{"name": "John Q. Doe", "phones": [], "associated_people": [], "future_field": 1}],
            "other_possible": [],
            "previous_addresses": [],
        },
    )
    svc = OccupantLookupService(_address_service(), provider=WhitePagesProProvider("k", transport=QueueTransport()), cache=cache)
    report = svc.lookup("123 Main St, Oklahoma City, OK 73102")
    assert report.from_cache is True
    assert report.high_confidence[0].name == "John Q. Doe"  # extra field ignored, not dropped


# --- Current vs former resident classification ----------------------------


def test_current_vs_former_resident_classification_and_sort():
    # Two people: one currently at the searched address, one only historically.
    payload = {
        "results": [
            {
                "id": "p1",
                "name": "Former Resident",
                "phones": [],
                "relatives": [],
                "current_addresses": [{"line1": "999 Other Rd", "zip": "73102"}],
                "historic_addresses": [{"full_address": "123 Main St, Oklahoma City, OK 73102", "line1": "123 Main St", "zip": "73102"}],
                "match_score": 90,
            },
            {
                "id": "p2",
                "name": "Current Resident",
                "phones": [],
                "relatives": [],
                "current_addresses": [{"line1": "123 Main St", "zip": "73102"}],
                "historic_addresses": [],
                "match_score": 88,
            },
        ],
        "metadata": {"result_count": 2},
    }
    provider = WhitePagesProProvider("k", transport=QueueTransport(HttpJsonResponse(status=200, payload=payload)))
    result = provider.lookup(_components())
    assert result.ok is True
    names = [o.name for o in result.high_confidence]
    # Current resident floats to the top even though their score is lower.
    assert names[0] == "Current Resident"
    by_name = {o.name: o for o in result.high_confidence}
    assert by_name["Current Resident"].is_current is True
    assert by_name["Former Resident"].is_current is False
    # The former resident's own prior address is attached to them.
    assert [p.address for p in by_name["Former Resident"].previous_addresses] == ["123 Main St, Oklahoma City, OK 73102"]
