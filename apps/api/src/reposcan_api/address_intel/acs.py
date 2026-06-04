"""US Census ACS area-context provider (optional, one free key).

Adds block-group occupancy context (owner vs renter, vacancy) for the area
around a matched address. This is the ONE source that needs a key — a free,
instant, email-only Census API key (https://api.census.gov/data/key_signup.html).
The whole address-intelligence function works WITHOUT it; when a key is present
(env CENSUS_API_KEY, wired in the API), this provider activates automatically.

Strictly AREA-level context, never individual — per Census API terms.
"""

from __future__ import annotations

from typing import Optional

from reposcan_contracts.address_intel import AreaContext

from .http_client import DEFAULT_TIMEOUT_S, JsonHttpClient, UrllibJsonClient

_ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
# B25003: tenure (owner/renter); B25002: occupancy (occupied/vacant).
_VARS = "B25003_001E,B25003_002E,B25003_003E,B25002_001E,B25002_003E"


class CensusAcsAreaProvider:
    name = "census_acs"

    def __init__(self, api_key: str, client: Optional[JsonHttpClient] = None, *, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self._api_key = api_key
        self._client = client or UrllibJsonClient()
        self._timeout = timeout

    def area_context(
        self,
        *,
        state_fips: Optional[str],
        census_tract: Optional[str],
        block_geoid: Optional[str],
    ) -> Optional[AreaContext]:
        # A 15-char block GEOID encodes state(2) county(3) tract(6) blockgroup(1)…
        if not block_geoid or len(block_geoid) < 12:
            return None
        state = block_geoid[0:2]
        county = block_geoid[2:5]
        tract = block_geoid[5:11]
        block_group = block_geoid[11]

        payload = self._client.get_json(
            _ACS_URL,
            params={
                "get": _VARS,
                "for": f"block group:{block_group}",
                "in": f"state:{state} county:{county} tract:{tract}",
                "key": self._api_key,
            },
            timeout=self._timeout,
        )
        return _parse_acs(payload)


def _parse_acs(payload: object) -> Optional[AreaContext]:
    # ACS returns [[header...],[values...]].
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    header = payload[0]
    row = payload[1]
    if not isinstance(header, list) or not isinstance(row, list):
        return None
    values = dict(zip(header, row))

    occupied = _to_int(values.get("B25003_001E"))
    owner = _to_int(values.get("B25003_002E"))
    renter = _to_int(values.get("B25003_003E"))
    total_units = _to_int(values.get("B25002_001E"))
    vacant = _to_int(values.get("B25002_003E"))

    owner_pct = _pct(owner, occupied)
    renter_pct = _pct(renter, occupied)
    vacancy_pct = _pct(vacant, total_units)

    parts: list[str] = []
    if owner_pct is not None:
        parts.append(f"{owner_pct:.0f}% owner-occupied")
    if vacancy_pct is not None:
        parts.append(f"{vacancy_pct:.0f}% vacancy")
    summary = ("Area: " + ", ".join(parts)) if parts else None

    if owner_pct is None and renter_pct is None and vacancy_pct is None and total_units is None:
        return None

    return AreaContext(
        owner_occupied_pct=owner_pct,
        renter_occupied_pct=renter_pct,
        vacancy_pct=vacancy_pct,
        total_housing_units=total_units,
        summary=summary,
    )


def _to_int(value: object) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pct(part: Optional[int], whole: Optional[int]) -> Optional[float]:
    if part is None or not whole:
        return None
    return round(100.0 * part / whole, 1)
