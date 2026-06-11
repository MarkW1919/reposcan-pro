"""Enformion provider parsing + WhitePages/Enformion merge (no network)."""

from __future__ import annotations

from reposcan_contracts.occupant_intel import Occupant, PreviousAddress
from reposcan_api.occupant_intel import (
    AddressComponents,
    EnformionProvider,
    HttpJsonResponse,
    MergeProvider,
    SkipTraceAudit,
    SkipTraceResult,
)

ENFORMION_RESPONSE = {
    "persons": [
        {
            "fullName": "John Q Doe",
            "name": {"firstName": "John", "middleName": "Q", "lastName": "Doe", "suffix": ""},
            "age": 42,
            "phoneNumbers": [{"phoneNumber": "(405) 555-1234", "phoneType": "Mobile"}],
            "relativesSummary": [{"firstName": "Jane", "lastName": "Doe"}],
            "addresses": [
                {
                    "houseNumber": "123", "streetName": "Main", "streetType": "St",
                    "city": "Oklahoma City", "state": "OK", "zip": "73102",
                    "fullAddress": "123 Main St; Oklahoma City, OK 73102",
                    "firstReportedDate": "5/5/2019", "lastReportedDate": "",
                },
                {
                    "houseNumber": "456", "streetName": "Oak", "streetType": "Ave",
                    "city": "Tulsa", "state": "OK", "zip": "74103",
                    "fullAddress": "456 Oak Ave; Tulsa, OK 74103",
                    "firstReportedDate": "2/1/2012", "lastReportedDate": "4/1/2019",
                },
            ],
            "score": 900,
        }
    ],
    "pagination": {},
}


class _PostTransport:
    def __init__(self, *responses: HttpJsonResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.headers: list[dict] = []

    def post(self, url, body, *, headers, timeout):  # noqa: ANN001
        self.calls.append(body)
        self.headers.append(dict(headers))
        return self._responses.pop(0) if self._responses else HttpJsonResponse(status=0, payload=None)


def _components() -> AddressComponents:
    return AddressComponents("123 Main St", "Oklahoma City", "OK", "73102")


def test_enformion_parses_date_ranges_and_current():
    transport = _PostTransport(HttpJsonResponse(status=200, payload=ENFORMION_RESPONSE))
    provider = EnformionProvider("profile-name", "secret-pass-1234", transport=transport)
    result = provider.lookup(_components())

    assert result.ok is True
    assert len(result.high_confidence) == 1
    occ = result.high_confidence[0]
    assert occ.name == "John Q Doe"
    assert occ.phones == ["(405) 555-1234 (Mobile)"]
    assert occ.associated_people == ["Jane Doe"]
    assert occ.is_current is True  # 123 Main has no last-seen -> still current
    labels = {p.address.split(",")[0]: p.date_range_label for p in occ.previous_addresses}
    assert labels["123 Main St"] == "May 2019 – Present"
    assert labels["456 Oak Ave"] == "Feb 2012 – Apr 2019"
    # Newest first.
    assert occ.previous_addresses[0].address.startswith("123 Main St")
    # Auth headers + password masking.
    assert transport.headers[0]["galaxy-ap-name"] == "profile-name"
    assert transport.headers[0]["galaxy-ap-password"] == "secret-pass-1234"
    assert result.audit.params_masked["ap_password"] == "***1234"
    assert "secret-pass-1234" not in str(result.audit.params_masked)


def test_enformion_unconfigured_without_credentials():
    provider = EnformionProvider("", "", transport=_PostTransport())
    result = provider.lookup(_components())
    assert result.ok is False
    assert result.audit.error == "unconfigured"


def test_enformion_offline_degrades():
    provider = EnformionProvider("n", "p", transport=_PostTransport(HttpJsonResponse(status=0, payload=None)))
    result = provider.lookup(_components())
    assert result.ok is False


# --- Merge -----------------------------------------------------------------


class _StubProvider:
    """Returns a fixed SkipTraceResult (stands in for WhitePages/Enformion)."""

    def __init__(self, name: str, result: SkipTraceResult) -> None:
        self.name = name
        self._result = result

    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        return self._result


def _audit(ok: bool) -> SkipTraceAudit:
    return SkipTraceAudit(endpoint="x", params_masked={}, success=ok)


def test_merge_enriches_whitepages_addresses_with_enformion_dates():
    # WhitePages: John (current), prior address 456 Oak with NO dates.
    wp = SkipTraceResult(
        source="WhitePages Pro",
        ok=True,
        high_confidence=[
            Occupant(
                name="John Q. Doe",
                is_current=True,
                previous_addresses=[PreviousAddress(address="456 Oak Ave, Tulsa, OK 74103")],
            )
        ],
        audit=_audit(True),
    )
    # Enformion: same prior address WITH a date range.
    en = SkipTraceResult(
        source="Enformion",
        ok=True,
        high_confidence=[
            Occupant(
                name="John Q Doe",
                is_current=True,
                previous_addresses=[
                    PreviousAddress(
                        address="456 Oak Ave, Tulsa, OK 74103",
                        date_first_seen="2012-02-01",
                        date_last_seen="2019-04-01",
                        date_range_label="Feb 2012 – Apr 2019",
                    )
                ],
            )
        ],
        audit=_audit(True),
    )
    merged = MergeProvider(_StubProvider("WhitePages Pro", wp), _StubProvider("Enformion", en)).lookup(_components())
    assert merged.ok is True
    prev = merged.high_confidence[0].previous_addresses[0]
    assert prev.address == "456 Oak Ave, Tulsa, OK 74103"
    assert prev.date_range_label == "Feb 2012 – Apr 2019"  # enriched from Enformion
    assert "WhitePages Pro + Enformion" in merged.source


def test_merge_degrades_to_primary_when_dates_provider_fails():
    wp = SkipTraceResult(
        source="WhitePages Pro",
        ok=True,
        high_confidence=[Occupant(name="John Q. Doe", is_current=True)],
        audit=_audit(True),
    )
    en_fail = SkipTraceResult(source="Enformion", ok=False, audit=_audit(False))
    merged = MergeProvider(_StubProvider("WhitePages Pro", wp), _StubProvider("Enformion", en_fail)).lookup(_components())
    assert merged.ok is True
    assert merged.high_confidence[0].name == "John Q. Doe"
    assert merged.source == "WhitePages Pro"  # unchanged; no enrichment


def test_merge_enformion_primary_fills_phones_and_adds_wp_only_people():
    # Enformion: John, current, dated addresses, but NO phones.
    en = SkipTraceResult(
        source="Enformion",
        ok=True,
        high_confidence=[
            Occupant(
                name="John Q Doe",
                is_current=True,
                phones=[],
                previous_addresses=[
                    PreviousAddress(address="123 Main St, Oklahoma City, OK 73102", date_last_seen="2026-01-01", date_range_label="Jan 2020 – Present"),
                ],
            )
        ],
        audit=_audit(True),
    )
    # WhitePages: John (with phones) + Bob (Enformion didn't return him).
    wp = SkipTraceResult(
        source="WhitePages Pro",
        ok=True,
        high_confidence=[
            Occupant(name="John Q. Doe", is_current=True, phones=["(405) 555-1234 (Mobile)"]),
            Occupant(name="Bob Roe", is_current=False, phones=["(405) 555-9999 (Landline)"]),
        ],
        audit=_audit(True),
    )
    merged = MergeProvider(_StubProvider("WhitePages Pro", wp), _StubProvider("Enformion", en)).lookup(_components())
    names = [o.name for o in (*merged.high_confidence, *merged.other_possible)]
    assert "John Q Doe" in names  # Enformion person is the base
    assert "Bob Roe" in names      # WhitePages-only person folded in
    john = next(o for o in merged.high_confidence if o.name == "John Q Doe")
    assert john.phones == ["(405) 555-1234 (Mobile)"]  # phone filled from WhitePages
    assert john.previous_addresses[0].date_range_label == "Jan 2020 – Present"  # date kept from Enformion
    assert john.is_current is True
    assert names[0] == "John Q Doe"  # current resident first
