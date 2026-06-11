"""OpenStreetMap / Overpass dwelling provider (keyless).

Infers dwelling type at a coordinate from OSM building=*/landuse=* tags near
the point. Keyless and fair-use friendly (one small bounded query per lookup,
identifying User-Agent). Best-effort: returns None on failure/offline.

Honest coverage note (surfaced as evidence, not hidden): US OSM building
tagging is uneven — a confident residential/commercial tag is meaningful, but
an untagged building is reported as unknown, never as "not residential".
"""

from __future__ import annotations

from typing import Optional

from reposcan_contracts.address_intel import DwellingType

from .http_client import DEFAULT_TIMEOUT_S, JsonHttpClient, UrllibJsonClient
from .providers import DwellingResult

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_RESIDENTIAL_BUILDINGS = {"house", "detached", "semidetached_house", "bungalow", "terrace", "residential", "cabin"}
_MULTI_UNIT_BUILDINGS = {"apartments", "dormitory", "residential_tower"}
_COMMERCIAL_BUILDINGS = {"commercial", "retail", "office", "industrial", "warehouse", "supermarket"}


class OverpassDwellingProvider:
    name = "osm_overpass"

    def __init__(
        self,
        client: Optional[JsonHttpClient] = None,
        *,
        radius_m: int = 35,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._client = client or UrllibJsonClient()
        self._radius_m = radius_m
        self._timeout = timeout

    def classify(self, latitude: float, longitude: float) -> Optional[DwellingResult]:
        query = (
            f"[out:json][timeout:{int(self._timeout)}];"
            f"(way(around:{self._radius_m},{latitude},{longitude})[building];"
            f"way(around:{self._radius_m},{latitude},{longitude})[landuse];);"
            f"out tags 12;"
        )
        payload = self._client.post_json(_OVERPASS_URL, data={"data": query}, timeout=self._timeout)
        if not isinstance(payload, dict):
            return None
        return _classify_elements(payload.get("elements"))


def _classify_elements(elements: object) -> Optional[DwellingResult]:
    if not isinstance(elements, list):
        return None

    buildings: list[str] = []
    landuses: list[str] = []
    for element in elements:
        tags = element.get("tags") if isinstance(element, dict) else None
        if not isinstance(tags, dict):
            continue
        if isinstance(tags.get("building"), str):
            buildings.append(tags["building"])
        if isinstance(tags.get("landuse"), str):
            landuses.append(tags["landuse"])

    # Building tags are the strongest signal; check most-specific first.
    for building in buildings:
        if building in _MULTI_UNIT_BUILDINGS:
            return DwellingResult(DwellingType.multi_unit, [f"OSM building={building}"])
    for building in buildings:
        if building in _RESIDENTIAL_BUILDINGS:
            return DwellingResult(DwellingType.single_family, [f"OSM building={building}"])
    for building in buildings:
        if building in _COMMERCIAL_BUILDINGS:
            return DwellingResult(DwellingType.commercial, [f"OSM building={building}"])

    # Fall back to area land use when no specific building subtype is tagged.
    for landuse in landuses:
        if landuse == "residential":
            return DwellingResult(DwellingType.single_family, ["OSM landuse=residential (area)"])
        if landuse in {"commercial", "retail", "industrial"}:
            return DwellingResult(DwellingType.commercial, [f"OSM landuse={landuse} (area)"])

    # A generic building=yes (geometry only) tells us a structure exists but not
    # its type — report unknown rather than guessing.
    return DwellingResult(DwellingType.unknown, [])
