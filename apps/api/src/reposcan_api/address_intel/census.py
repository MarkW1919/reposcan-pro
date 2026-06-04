"""US Census Geocoder provider (keyless).

Resolves an address to a standardized address, coordinates, and census
geographies (state/county/tract/block FIPS) in one keyless call. Public-domain
US government service; no API key or account. Best-effort: parse failures and
non-matches return None / an unmatched result, never raise.

Endpoint: https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress
"""

from __future__ import annotations

from typing import Optional

from reposcan_contracts.address_intel import AddressMatchQuality

from .http_client import DEFAULT_TIMEOUT_S, JsonHttpClient, UrllibJsonClient
from .providers import GeocodeResult

_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"


class CensusGeocoderProvider:
    name = "census_geocoder"

    def __init__(self, client: Optional[JsonHttpClient] = None, *, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self._client = client or UrllibJsonClient()
        self._timeout = timeout

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        payload = self._client.get_json(
            _GEOCODER_URL,
            params={
                "address": address,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            },
            timeout=self._timeout,
        )
        if not isinstance(payload, dict):
            return None
        return _parse_geocode(payload)


def _parse_geocode(payload: dict) -> GeocodeResult:
    matches = (((payload.get("result") or {}).get("addressMatches")) or [])
    if not isinstance(matches, list) or not matches:
        return GeocodeResult(matched=False, match_quality=AddressMatchQuality.none)

    match = matches[0] if isinstance(matches[0], dict) else {}
    coords = match.get("coordinates") if isinstance(match.get("coordinates"), dict) else {}
    latitude = _as_float(coords.get("y"))
    longitude = _as_float(coords.get("x"))

    geographies = match.get("geographies") if isinstance(match.get("geographies"), dict) else {}
    block = _first(geographies.get("Census Blocks") or geographies.get("2020 Census Blocks"))
    county = _first(geographies.get("Counties"))

    return GeocodeResult(
        matched=True,
        match_quality=AddressMatchQuality.exact,
        standardized_address=match.get("matchedAddress"),
        latitude=latitude,
        longitude=longitude,
        state_fips=(block or {}).get("STATE"),
        county_name=(county or {}).get("NAME"),
        census_tract=(block or {}).get("TRACT"),
        block_geoid=(block or {}).get("GEOID"),
    )


def _first(value: object) -> Optional[dict]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _as_float(value: object) -> Optional[float]:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
