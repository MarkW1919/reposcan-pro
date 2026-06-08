"""FastAPI application skeleton for RepoScan Pro."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import difflib
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from reposcan_contracts.address_intel import AddressIntelligenceReport
from reposcan_contracts.occupant_intel import OccupantIntelligenceReport
from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.config.deployment import ApiRole, DeploymentConfig
from reposcan_contracts.dispatch import DispatchAssignmentRecord, DispatchAssignmentStatus
from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord, FollowUpStatus
from reposcan_contracts.health import HealthResponse, HealthState
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorCapabilities, OperatorPrincipal, OperatorSessionRecord
from reposcan_contracts.popup import PopupActivityEvent, PopupEventType
from reposcan_contracts.review import ReviewRecord
from reposcan_inference import DemoRunInProgressError, DemoRunStatus as RuntimeDemoRunStatus, HeadlessDemoRunManager
from reposcan_storage.service import (
    AssignmentNotFoundError,
    AlertNotFoundError,
    DetectionNotFoundError,
    FollowUpNotFoundError,
    HotlistNotFoundError,
    StorageService,
    create_development_storage_service,
)

from .models import (
    AddressSearchResponse,
    AddressSearchSuggestion,
    AlertUpdateSubmission,
    AlertSearchResponse,
    ApiAuditEvent,
    ApiVersionInfo,
    AuditEventResponse,
    AuditOutcome,
    DashboardCounts,
    DashboardOverview,
    DetectionSearchResponse,
    DispatchAssignmentSubmission,
    DemoRunSubmission,
    DemoRunSummary,
    DemoRuntimeStatus,
    EdgeCaptureState,
    EdgeRuntimeCommand,
    EdgeRuntimeCommandSubmission,
    EdgeRuntimeHeartbeatSubmission,
    EdgeRuntimeStatus,
    FollowUpSubmission,
    GeoSearchFilters,
    GeoShapeType,
    HotlistSubmission,
    OperatorSessionHeartbeatSubmission,
    ReverseAddressResponse,
    ReviewSubmission,
    SearchPageInfo,
    SearchPlateMatchMode,
)
from .address_intel import (
    AddressIntelligenceService,
    CensusAcsAreaProvider,
    CensusGeocoderProvider,
    InMemoryReportCache,
    OverpassDwellingProvider,
)
from .occupant_intel import (
    AddressComponents,
    OccupantLookupService,
    SqliteOccupantCache,
    WHITEPAGES_MODE,
    WhitePagesProProvider,
)
from .audit import ApiAuditLogger
from .security import ApiAccessController, ApiPrincipalContext, principal_details

_DASHBOARD_SUPPORTING_RECORD_LIMIT = 200
_ADDRESS_SEARCH_PROVIDER = "nominatim"
_ADDRESS_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
_ADDRESS_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_ADDRESS_SEARCH_TIMEOUT_SECONDS = 3.0
_ADDRESS_SEARCH_CACHE_FRESH_SECONDS = 300.0
_ADDRESS_SEARCH_CACHE_STALE_SECONDS = 1800.0
_ADDRESS_SEARCH_CACHE_MAX_ENTRIES = 128
_ADDRESS_SEARCH_FETCH_LIMIT_MULTIPLIER = 3
_ADDRESS_SEARCH_FETCH_LIMIT_MAX = 12
_ADDRESS_SEARCH_VIEWBOX_RADIUS_MILES = 40.0
_ADDRESS_SEARCH_ALLOWED_STATES = {"texas", "oklahoma"}
_ADDRESS_SEARCH_ALLOWED_STATE_CODES = {"tx", "ok"}
_ADDRESS_SEARCH_SPELLING_LEXICON = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "hampshire",
    "jersey",
    "mexico",
    "york",
    "carolina",
    "dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode",
    "island",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "wisconsin",
    "wyoming",
    "north",
    "south",
    "east",
    "west",
    "northeast",
    "northwest",
    "southeast",
    "southwest",
    "street",
    "road",
    "avenue",
    "boulevard",
    "drive",
    "lane",
    "court",
    "circle",
    "trail",
    "parkway",
    "highway",
    "mount",
    "fort",
    "city",
    "county",
    "ok",
    "tx",
}

_ADDRESS_TOKEN_ALIASES = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
    "st": "street",
    "rd": "road",
    "ave": "avenue",
    "blvd": "boulevard",
    "dr": "drive",
    "ln": "lane",
    "ct": "court",
    "cir": "circle",
    "trl": "trail",
    "pkwy": "parkway",
    "hwy": "highway",
    "mt": "mount",
    "ft": "fort",
}


@dataclass(frozen=True)
class _AddressSearchCacheEntry:
    cached_at_monotonic: float
    results: tuple[AddressSearchSuggestion, ...]


_address_search_cache: dict[tuple[str, int, str, float | None, float | None], _AddressSearchCacheEntry] = {}
_address_search_cache_lock = RLock()
_reverse_address_cache: dict[tuple[float, float], tuple[float, ReverseAddressResponse]] = {}
_reverse_address_cache_lock = RLock()


def _build_default_edge_runtime_status() -> EdgeRuntimeStatus:
    return EdgeRuntimeStatus(
        edge_node_id="jetson-orin-nano",
        capture_state=EdgeCaptureState.unknown,
        desired_capture_state=EdgeCaptureState.stopped,
        active_camera_count=0,
        total_camera_count=0,
        inference_runtime="pending-hardware",
        plate_ocr_provider="fast-alpr",
        vehicle_attribute_provider="hf_vehicle_classifier",
        primary_ai_camera_id="cam_lpr_primary",
        secondary_context_camera_id="cam_overview_context",
        deferred_vehicle_recognition_enabled=True,
        message="Waiting for edge hardware heartbeat.",
    )


class AddressSearchProviderError(RuntimeError):
    """Raised when the upstream address search provider cannot be reached cleanly."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_OCCUPANT_CONFIG_PATH = "configs/occupant_intel.yaml"


def _resolve_occupant_provider_name() -> str:
    """Occupant provider toggle: env override > committed config file > default.

    The provider toggle is non-secret config; the API key is read separately from
    the environment and never from this file.
    """
    env_value = os.environ.get("OCCUPANT_PROVIDER", "").strip().lower()
    if env_value:
        return env_value
    try:
        import yaml  # available via the deployment config loader

        with open(_OCCUPANT_CONFIG_PATH, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        provider = str(data.get("provider", "")).strip().lower()
        if provider:
            return provider
    except (OSError, ValueError):
        pass
    return WHITEPAGES_MODE


def _best_detection_confidence(detection: DetectionRecord) -> float:
    if detection.plate_confidence is not None:
        return detection.plate_confidence
    if detection.plate_candidates:
        return max(candidate.confidence for candidate in detection.plate_candidates)
    return 0.0


def _build_address_popup_note(detection: DetectionRecord) -> str:
    if detection.plate_text:
        return "General detection is ready to surface when active scan mode is enabled."
    return "Vehicle detection is available, but the best plate read is still pending or occluded."


def _build_alert_popup_note(alert: AlertRecord) -> str | None:
    parts = [alert.notes, alert.response_notes]
    note = " | ".join(part for part in parts if part)
    return note or None


def _normalize_address_token(token: str) -> str:
    normalized = token.strip().lower()
    return _ADDRESS_TOKEN_ALIASES.get(normalized, normalized)


def _address_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return [_normalize_address_token(token) for token in re.findall(r"[a-z0-9]+", value.lower())]


def _query_house_number(tokens: list[str]) -> str | None:
    for token in tokens:
        if token.isdigit():
            return token
    return None


def _bias_viewbox(latitude: float, longitude: float, *, radius_miles: float) -> str:
    lat_delta = radius_miles / 69.0
    lng_scale = max(math.cos(math.radians(latitude)), 0.15)
    lng_delta = radius_miles / (69.0 * lng_scale)
    west = longitude - lng_delta
    east = longitude + lng_delta
    north = latitude + lat_delta
    south = latitude - lat_delta
    return f"{west:.6f},{north:.6f},{east:.6f},{south:.6f}"


def _haversine_miles(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    earth_radius_miles = 3958.7613
    lat_a_rad = math.radians(lat_a)
    lat_b_rad = math.radians(lat_b)
    delta_lat = lat_b_rad - lat_a_rad
    delta_lng = math.radians(lng_b - lng_a)
    sin_lat = math.sin(delta_lat / 2.0)
    sin_lng = math.sin(delta_lng / 2.0)
    value = sin_lat**2 + math.cos(lat_a_rad) * math.cos(lat_b_rad) * sin_lng**2
    return 2.0 * earth_radius_miles * math.asin(min(1.0, math.sqrt(value)))


def _candidate_text_parts(item: dict[str, object]) -> list[str]:
    address = item.get("address")
    address_parts = address if isinstance(address, dict) else {}
    parts = [
        item.get("display_name"),
        item.get("name"),
        address_parts.get("amenity"),
        address_parts.get("house_number"),
        address_parts.get("road"),
        address_parts.get("suburb"),
        address_parts.get("city"),
        address_parts.get("town"),
        address_parts.get("village"),
        address_parts.get("county"),
        address_parts.get("state"),
        address_parts.get("postcode"),
    ]
    return [str(part) for part in parts if isinstance(part, str) and part.strip()]


def _candidate_address_parts(item: dict[str, object]) -> dict[str, object]:
    address = item.get("address")
    return address if isinstance(address, dict) else {}


def _candidate_in_allowed_states(item: dict[str, object]) -> bool:
    address_parts = _candidate_address_parts(item)
    state_value = str(address_parts.get("state", "")).strip().lower()
    state_code = str(address_parts.get("state_code", "")).strip().lower()
    if state_value in _ADDRESS_SEARCH_ALLOWED_STATES:
        return True
    if state_code in _ADDRESS_SEARCH_ALLOWED_STATE_CODES:
        return True
    display_name = str(item.get("display_name", "")).lower()
    return any(state_name in display_name for state_name in _ADDRESS_SEARCH_ALLOWED_STATES)


def _address_spelling_variant(query: str) -> str | None:
    pieces = re.findall(r"[a-z0-9]+|[^a-z0-9]+", query.lower())
    corrected: list[str] = []
    changed = False
    for piece in pieces:
        if not piece.isalpha() or len(piece) < 5 or piece in _ADDRESS_SEARCH_SPELLING_LEXICON:
            corrected.append(piece)
            continue
        replacement = difflib.get_close_matches(piece, sorted(_ADDRESS_SEARCH_SPELLING_LEXICON), n=1, cutoff=0.88)
        if replacement:
            corrected.append(replacement[0])
            changed = True
        else:
            corrected.append(piece)
    if not changed:
        return None
    return "".join(corrected)


def _address_match_score(
    query: str,
    item: dict[str, object],
    *,
    bias_latitude: float | None,
    bias_longitude: float | None,
) -> float:
    query_tokens = _address_tokens(query)
    if not query_tokens:
        return 0.0

    candidate_text = " ".join(_candidate_text_parts(item))
    candidate_tokens = _address_tokens(candidate_text)
    candidate_token_set = set(candidate_tokens)
    score = 0.0

    normalized_query = " ".join(query_tokens)
    normalized_candidate = " ".join(candidate_tokens)
    if normalized_query and normalized_query in normalized_candidate:
        score += 90.0
    if normalized_query and normalized_candidate.startswith(normalized_query):
        score += 35.0

    house_number = _query_house_number(query_tokens)
    address_parts = _candidate_address_parts(item)
    candidate_house_number = _query_house_number(_address_tokens(str(address_parts.get("house_number", ""))))
    for token in query_tokens:
        if token in candidate_token_set:
            score += 18.0 if token.isdigit() else 5.0
        else:
            score -= 12.0 if token.isdigit() else 1.5
    if house_number:
        if candidate_house_number == house_number:
            score += 70.0
        elif candidate_house_number:
            score -= 40.0

    importance = item.get("importance")
    try:
        score += float(importance) * 20.0
    except (TypeError, ValueError):
        pass

    if bias_latitude is not None and bias_longitude is not None:
        try:
            candidate_latitude = float(item["lat"])
            candidate_longitude = float(item["lon"])
            distance_miles = _haversine_miles(bias_latitude, bias_longitude, candidate_latitude, candidate_longitude)
            if distance_miles <= 10.0:
                score += 35.0
            elif distance_miles <= 30.0:
                score += 22.0
            elif distance_miles <= 75.0:
                score += 10.0
            elif distance_miles >= 250.0:
                score -= 20.0
        except (KeyError, TypeError, ValueError):
            pass

    if not _candidate_in_allowed_states(item):
        score -= 250.0

    return score


def _sorted_address_payload(
    payload: list[object],
    *,
    query: str,
    bias_latitude: float | None,
    bias_longitude: float | None,
) -> list[dict[str, object]]:
    ranked: list[tuple[float, float, dict[str, object]]] = []
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        if not _candidate_in_allowed_states(raw_item):
            continue
        try:
            importance = float(raw_item.get("importance") or 0.0)
        except (TypeError, ValueError):
            importance = 0.0
        ranked.append(
            (
                _address_match_score(
                    query,
                    raw_item,
                    bias_latitude=bias_latitude,
                    bias_longitude=bias_longitude,
                ),
                importance,
                raw_item,
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked]


def _address_search_cache_key(
    query: str,
    *,
    limit: int,
    countrycodes: str,
    bias_latitude: float | None,
    bias_longitude: float | None,
) -> tuple[str, int, str, float | None, float | None]:
    normalized_query = " ".join(query.strip().lower().split())
    rounded_latitude = round(bias_latitude, 2) if bias_latitude is not None else None
    rounded_longitude = round(bias_longitude, 2) if bias_longitude is not None else None
    return normalized_query, limit, countrycodes.strip().lower(), rounded_latitude, rounded_longitude


def _get_cached_address_results(
    query: str,
    *,
    limit: int,
    countrycodes: str,
    bias_latitude: float | None,
    bias_longitude: float | None,
    max_age_seconds: float,
) -> list[AddressSearchSuggestion] | None:
    cache_key = _address_search_cache_key(
        query,
        limit=limit,
        countrycodes=countrycodes,
        bias_latitude=bias_latitude,
        bias_longitude=bias_longitude,
    )
    with _address_search_cache_lock:
        entry = _address_search_cache.get(cache_key)
        if entry is None:
            return None
        age_seconds = time.monotonic() - entry.cached_at_monotonic
        if age_seconds > max_age_seconds:
            return None
        return [item.model_copy(deep=True) for item in entry.results]


def _store_cached_address_results(
    query: str,
    *,
    limit: int,
    countrycodes: str,
    bias_latitude: float | None,
    bias_longitude: float | None,
    results: list[AddressSearchSuggestion],
) -> None:
    cache_key = _address_search_cache_key(
        query,
        limit=limit,
        countrycodes=countrycodes,
        bias_latitude=bias_latitude,
        bias_longitude=bias_longitude,
    )
    entry = _AddressSearchCacheEntry(
        cached_at_monotonic=time.monotonic(),
        results=tuple(item.model_copy(deep=True) for item in results),
    )
    with _address_search_cache_lock:
        _address_search_cache[cache_key] = entry
        if len(_address_search_cache) <= _ADDRESS_SEARCH_CACHE_MAX_ENTRIES:
            return
        oldest_key = min(
            _address_search_cache.items(),
            key=lambda item: item[1].cached_at_monotonic,
        )[0]
        _address_search_cache.pop(oldest_key, None)


def _reverse_address_cache_key(latitude: float, longitude: float) -> tuple[float, float]:
    return round(latitude, 4), round(longitude, 4)


def _get_cached_reverse_address(latitude: float, longitude: float, *, max_age_seconds: float) -> ReverseAddressResponse | None:
    cache_key = _reverse_address_cache_key(latitude, longitude)
    with _reverse_address_cache_lock:
        entry = _reverse_address_cache.get(cache_key)
        if entry is None:
            return None
        cached_at_monotonic, result = entry
        if time.monotonic() - cached_at_monotonic > max_age_seconds:
            return None
        return result.model_copy(deep=True)


def _store_cached_reverse_address(result: ReverseAddressResponse) -> None:
    cache_key = _reverse_address_cache_key(result.latitude, result.longitude)
    with _reverse_address_cache_lock:
        _reverse_address_cache[cache_key] = (time.monotonic(), result.model_copy(deep=True))
        if len(_reverse_address_cache) <= _ADDRESS_SEARCH_CACHE_MAX_ENTRIES:
            return
        oldest_key = min(_reverse_address_cache.items(), key=lambda item: item[1][0])[0]
        _reverse_address_cache.pop(oldest_key, None)


def _reverse_address_lookup(latitude: float, longitude: float) -> ReverseAddressResponse:
    cached_result = _get_cached_reverse_address(
        latitude,
        longitude,
        max_age_seconds=_ADDRESS_SEARCH_CACHE_FRESH_SECONDS,
    )
    if cached_result is not None:
        return cached_result

    params = urlencode(
        {
            "lat": f"{latitude:.7f}",
            "lon": f"{longitude:.7f}",
            "format": "jsonv2",
            "addressdetails": "1",
            "zoom": "18",
        }
    )
    request = UrlRequest(
        f"{_ADDRESS_REVERSE_URL}?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "RepoScanPro/1.0 (repossession field tool)",
        },
    )

    try:
        with urlopen(request, timeout=_ADDRESS_SEARCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        stale_result = _get_cached_reverse_address(
            latitude,
            longitude,
            max_age_seconds=_ADDRESS_SEARCH_CACHE_STALE_SECONDS,
        )
        if stale_result is not None:
            return stale_result
        raise AddressSearchProviderError("Address reverse-geocode provider unavailable") from exc

    if not isinstance(payload, dict):
        raise AddressSearchProviderError("Address reverse-geocode provider returned invalid data")

    address = payload.get("address")
    address_parts = address if isinstance(address, dict) else {}
    display_name = str(payload.get("display_name") or "").strip()
    if not display_name:
        road = str(address_parts.get("road") or address_parts.get("pedestrian") or address_parts.get("path") or "").strip()
        house_number = str(address_parts.get("house_number") or "").strip()
        display_name = " ".join(part for part in (house_number, road) if part) or f"{latitude:.5f}, {longitude:.5f}"

    result = ReverseAddressResponse(
        display_name=display_name,
        latitude=latitude,
        longitude=longitude,
        house_number=str(address_parts.get("house_number") or "").strip() or None,
        road=str(address_parts.get("road") or address_parts.get("pedestrian") or address_parts.get("path") or "").strip() or None,
        city=str(
            address_parts.get("city")
            or address_parts.get("town")
            or address_parts.get("village")
            or address_parts.get("hamlet")
            or ""
        ).strip()
        or None,
        state=str(address_parts.get("state") or "").strip() or None,
        postal_code=str(address_parts.get("postcode") or "").strip() or None,
        provider=_ADDRESS_SEARCH_PROVIDER,
    )
    _store_cached_reverse_address(result)
    return result


def _search_address_candidates(
    query: str,
    *,
    limit: int,
    countrycodes: str = "us",
    bias_latitude: float | None = None,
    bias_longitude: float | None = None,
) -> list[AddressSearchSuggestion]:
    suggestions = _search_address_candidates_once(
        query,
        limit=limit,
        countrycodes=countrycodes,
        bias_latitude=bias_latitude,
        bias_longitude=bias_longitude,
    )
    if suggestions:
        return suggestions
    spelling_variant = _address_spelling_variant(query)
    if spelling_variant and spelling_variant != query.strip().lower():
        return _search_address_candidates_once(
            spelling_variant,
            limit=limit,
            countrycodes=countrycodes,
            bias_latitude=bias_latitude,
            bias_longitude=bias_longitude,
        )
    return suggestions


def _search_address_candidates_once(
    query: str,
    *,
    limit: int,
    countrycodes: str,
    bias_latitude: float | None,
    bias_longitude: float | None,
) -> list[AddressSearchSuggestion]:
    trimmed = query.strip()
    if not trimmed:
        return []

    cached_results = _get_cached_address_results(
        trimmed,
        limit=limit,
        countrycodes=countrycodes,
        bias_latitude=bias_latitude,
        bias_longitude=bias_longitude,
        max_age_seconds=_ADDRESS_SEARCH_CACHE_FRESH_SECONDS,
    )
    if cached_results is not None:
        return cached_results

    request_params = {
        "q": trimmed,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": str(min(_ADDRESS_SEARCH_FETCH_LIMIT_MAX, max(limit, limit * _ADDRESS_SEARCH_FETCH_LIMIT_MULTIPLIER))),
        "countrycodes": countrycodes,
        "dedupe": "1",
    }
    if bias_latitude is not None and bias_longitude is not None:
        request_params["viewbox"] = _bias_viewbox(
            bias_latitude,
            bias_longitude,
            radius_miles=_ADDRESS_SEARCH_VIEWBOX_RADIUS_MILES,
        )
    params = urlencode(request_params)
    request = UrlRequest(
        f"{_ADDRESS_SEARCH_URL}?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "RepoScanPro/1.0 (repossession field tool)",
        },
    )

    try:
        with urlopen(request, timeout=_ADDRESS_SEARCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        stale_results = _get_cached_address_results(
            trimmed,
            limit=limit,
            countrycodes=countrycodes,
            bias_latitude=bias_latitude,
            bias_longitude=bias_longitude,
            max_age_seconds=_ADDRESS_SEARCH_CACHE_STALE_SECONDS,
        )
        if stale_results is not None:
            return stale_results
        raise AddressSearchProviderError("Address search provider unavailable") from exc

    suggestions: list[AddressSearchSuggestion] = []
    for item in _sorted_address_payload(
        payload,
        query=trimmed,
        bias_latitude=bias_latitude,
        bias_longitude=bias_longitude,
    ):
        try:
            suggestions.append(
                AddressSearchSuggestion(
                    suggestion_id=str(item["place_id"]),
                    display_name=str(item["display_name"]),
                    latitude=float(item["lat"]),
                    longitude=float(item["lon"]),
                    provider=_ADDRESS_SEARCH_PROVIDER,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
        if len(suggestions) >= limit:
            break
    _store_cached_address_results(
        trimmed,
        limit=limit,
        countrycodes=countrycodes,
        bias_latitude=bias_latitude,
        bias_longitude=bias_longitude,
        results=suggestions,
    )
    return suggestions


def _geo_search_kwargs(geo_filters: GeoSearchFilters) -> dict[str, object]:
    polygon_points = geo_filters.polygon_points()
    shape = geo_filters.geo_shape.value if geo_filters.geo_shape is not None else None

    if shape is None:
        if polygon_points:
            shape = "polygon"
        elif any(
            value is not None
            for value in (
                geo_filters.geo_center_latitude,
                geo_filters.geo_center_longitude,
                geo_filters.geo_radius_meters,
            )
        ):
            shape = "circle"

    if shape == "circle":
        if polygon_points:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="polygon points cannot be combined with circle geo filters",
            )
        if None in (
            geo_filters.geo_center_latitude,
            geo_filters.geo_center_longitude,
            geo_filters.geo_radius_meters,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="geo center latitude, geo center longitude, and geo radius meters are required for circle search",
            )
    elif shape == "polygon":
        if any(
            value is not None
            for value in (
                geo_filters.geo_center_latitude,
                geo_filters.geo_center_longitude,
                geo_filters.geo_radius_meters,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="circle geo filters cannot be combined with polygon geo filters",
            )
        if len(polygon_points) < 3:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="at least three geo polygon points are required for polygon search",
            )
    elif any(
        value is not None
        for value in (
            geo_filters.geo_center_latitude,
            geo_filters.geo_center_longitude,
            geo_filters.geo_radius_meters,
            *polygon_points,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="geo_shape must be circle or polygon when geo filters are supplied",
        )

    return {
        "geo_shape_type": shape,
        "geo_center_latitude": geo_filters.geo_center_latitude,
        "geo_center_longitude": geo_filters.geo_center_longitude,
        "geo_radius_meters": geo_filters.geo_radius_meters,
        "geo_polygon_points": polygon_points,
    }


def _resolve_media_path(media_ref: str | None, media_root: Path) -> Path | None:
    if not media_ref:
        return None

    candidate = Path(media_ref)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None

    resolved = candidate.resolve(strict=False)
    if resolved.is_file():
        return resolved

    rooted_base = media_root.parent if candidate.parts and candidate.parts[0] == media_root.name else media_root
    rooted = (rooted_base / candidate).resolve(strict=False)
    if rooted.is_file():
        return rooted

    return None


def _build_popup_activity(
    *,
    detections: list[DetectionRecord],
    alerts: list[AlertRecord],
    limit: int,
) -> list[PopupActivityEvent]:
    detections_by_id = {record.detection_id: record for record in detections}
    alert_detection_ids: set[str] = set()
    events: list[PopupActivityEvent] = []

    for alert in alerts:
        alert_detection_ids.add(alert.detection_id)
        if alert.status == AlertStatus.dismissed:
            continue
        detection = detections_by_id.get(alert.detection_id)
        events.append(
            PopupActivityEvent(
                event_id=f"popup_{alert.alert_id}",
                event_type=PopupEventType.hotlist,
                source_record_id=alert.alert_id,
                detection_id=alert.detection_id,
                timestamp_utc=alert.timestamp_utc,
                camera_id=alert.camera_id,
                plate_text=alert.matched_plate_text,
                confidence=alert.match_confidence,
                vehicle_color=detection.vehicle_color if detection is not None else None,
                vehicle_make=detection.vehicle_make if detection is not None else None,
                vehicle_model=detection.vehicle_model if detection is not None else None,
                optional_vehicle_year=detection.optional_vehicle_year if detection is not None else None,
                hotlist_label=alert.hotlist_label,
                gps_latitude=alert.gps_latitude if alert.gps_latitude is not None else detection.gps_latitude if detection is not None else None,
                gps_longitude=alert.gps_longitude if alert.gps_longitude is not None else detection.gps_longitude if detection is not None else None,
                note=_build_alert_popup_note(alert),
            )
        )

    for detection in detections:
        if detection.detection_id in alert_detection_ids:
            continue

        events.append(
            PopupActivityEvent(
                event_id=f"popup_{detection.detection_id}",
                event_type=PopupEventType.address,
                source_record_id=detection.detection_id,
                detection_id=detection.detection_id,
                timestamp_utc=detection.timestamp_utc,
                camera_id=detection.camera_id,
                plate_text=detection.plate_text,
                confidence=_best_detection_confidence(detection),
                vehicle_color=detection.vehicle_color,
                vehicle_make=detection.vehicle_make,
                vehicle_model=detection.vehicle_model,
                optional_vehicle_year=detection.optional_vehicle_year,
                gps_latitude=detection.gps_latitude,
                gps_longitude=detection.gps_longitude,
                note=_build_address_popup_note(detection),
            )
        )

    events.sort(key=lambda event: event.timestamp_utc, reverse=True)
    return events[:limit]


def _build_demo_runtime_status(status: RuntimeDemoRunStatus) -> DemoRuntimeStatus:
    summary = None
    if status.summary is not None:
        summary = DemoRunSummary(
            frames_captured=status.summary.frames_captured,
            candidates_processed=status.summary.candidates_processed,
            tracks_finalized=status.summary.tracks_finalized,
            stored_detection_ids=status.summary.stored_detection_ids,
            created_alert_ids=status.summary.created_alert_ids,
        )

    return DemoRuntimeStatus(
        state=status.state,
        run_id=status.run_id,
        started_at_utc=status.started_at_utc,
        completed_at_utc=status.completed_at_utc,
        frames_directory=status.frames_directory,
        glob_pattern=status.glob_pattern,
        sequence_id=status.sequence_id,
        plate_text=status.plate_text,
        error_message=status.error_message,
        summary=summary,
    )


def _build_operator_capabilities(principal: ApiPrincipalContext) -> OperatorCapabilities:
    roles = set(principal.roles)
    can_operate = ApiRole.operator in roles or ApiRole.admin in roles
    return OperatorCapabilities(
        can_submit_reviews=can_operate,
        can_update_alerts=can_operate,
        can_manage_hotlists=ApiRole.admin in roles,
        can_manage_follow_ups=can_operate,
        can_manage_dispatch=can_operate,
        can_start_demo_runs=can_operate,
        can_control_edge_runtime=can_operate,
        can_view_audit=ApiRole.admin in roles or ApiRole.integrator in roles,
    )


def _build_operator_principal(principal: ApiPrincipalContext) -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id=principal.principal_id,
        display_name=principal.display_name,
        authenticated=principal.authenticated,
        roles=list(principal.roles),
        capabilities=_build_operator_capabilities(principal),
    )


def create_app(
    storage_service: StorageService | None = None,
    demo_run_manager: HeadlessDemoRunManager | None = None,
    deployment_config: DeploymentConfig | None = None,
    address_intel_service: AddressIntelligenceService | None = None,
    occupant_intel_service: OccupantLookupService | None = None,
) -> FastAPI:
    service = storage_service or create_development_storage_service()
    deployment = deployment_config or service.deployment_config or load_deployment_config("configs/deployments/local-dev.yaml")
    demo_manager = demo_run_manager or HeadlessDemoRunManager(storage_service=service)
    audit_logger = ApiAuditLogger(
        deployment.api.audit.log_root,
        enabled=deployment.api.audit.enabled,
        max_read_limit=deployment.api.audit.max_read_limit,
    )
    access_controller = ApiAccessController(deployment.api, audit_logger=audit_logger)

    app = FastAPI(
        title="RepoScan Pro API",
        version="0.1.0",
        description="Edge-first API for health, detections, alerts, reviews, hotlists, search, audit, and dashboard overview.",
        docs_url="/docs" if deployment.api.hardening.expose_docs else None,
        redoc_url="/redoc" if deployment.api.hardening.expose_docs else None,
        openapi_url="/openapi.json" if deployment.api.hardening.expose_docs else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=deployment.api.hardening.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=deployment.api.hardening.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.storage_service = service
    app.state.demo_run_manager = demo_manager
    app.state.deployment_config = deployment
    app.state.audit_logger = audit_logger
    app.state.access_controller = access_controller

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid4().hex[:12]}"
        request.state.request_id = request_id
        request.state.utcnow = _utcnow
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error", "request_id": request_id},
            )
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Api-Version"] = deployment.api.versioning.current_version
        if deployment.api.hardening.add_security_headers:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
        rate_limit_limit = getattr(request.state, "rate_limit_limit", None)
        rate_limit_remaining = getattr(request.state, "rate_limit_remaining", None)
        if rate_limit_limit is not None and rate_limit_remaining is not None:
            response.headers["X-RateLimit-Limit"] = str(rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_remaining)
        return response

    def build_health_response() -> HealthResponse:
        dependencies = service.dependency_health()
        state = (
            HealthState.down
            if any(dep.state == HealthState.down for dep in dependencies)
            else HealthState.degraded
            if any(dep.state == HealthState.degraded for dep in dependencies)
            else HealthState.ok
        )
        return HealthResponse(
            service="api",
            version=app.version,
            state=state,
            timestamp_utc=_utcnow(),
            dependencies=dependencies,
        )

    def build_version_info() -> ApiVersionInfo:
        return ApiVersionInfo(
            service="api",
            package_version=app.version,
            api_version=deployment.api.versioning.current_version,
            canonical_prefix=deployment.api.versioning.canonical_prefix,
            legacy_routes_enabled=deployment.api.versioning.enable_legacy_routes,
            auth_enabled=deployment.api.security.enabled,
            rate_limit_enabled=deployment.api.rate_limit.enabled,
        )

    edge_runtime_lock = RLock()
    edge_runtime_status = _build_default_edge_runtime_status()

    def edge_runtime_snapshot() -> EdgeRuntimeStatus:
        with edge_runtime_lock:
            return edge_runtime_status.model_copy(deep=True)

    def update_edge_runtime(status_update: EdgeRuntimeStatus) -> EdgeRuntimeStatus:
        nonlocal edge_runtime_status
        with edge_runtime_lock:
            edge_runtime_status = status_update
            return edge_runtime_status.model_copy(deep=True)

    def desired_state_for_command(command: EdgeRuntimeCommand) -> EdgeCaptureState:
        if command == EdgeRuntimeCommand.start_capture:
            return EdgeCaptureState.running
        if command == EdgeRuntimeCommand.stop_capture:
            return EdgeCaptureState.stopped
        if command == EdgeRuntimeCommand.restart_capture:
            return EdgeCaptureState.running
        if command == EdgeRuntimeCommand.mark_faulted:
            return EdgeCaptureState.faulted
        return EdgeCaptureState.unknown

    def record_audit(
        request: Request,
        *,
        principal: ApiPrincipalContext | None,
        action: str,
        outcome: AuditOutcome,
        target_type: str | None = None,
        target_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        if not deployment.api.audit.enabled:
            return
        principal_id, principal_roles = principal_details(principal)
        audit_logger.record(
            ApiAuditEvent(
                event_id=f"audit_{uuid4().hex[:12]}",
                occurred_at_utc=_utcnow(),
                request_id=request.state.request_id,
                principal_id=principal_id,
                principal_roles=principal_roles,
                action=action,
                outcome=outcome,
                method=request.method,
                path=request.url.path,
                target_type=target_type,
                target_id=target_id,
                details=details or {},
            )
        )

    # Address intelligence: zero-cost keyless public-data lookup for a staged
    # destination. Providers are best-effort (degrade offline); the in-memory
    # cache persists resolved reports for the app's lifetime so repeat/offline
    # lookups are instant. Census ACS area context can be added later via a free
    # key without changing this wiring.
    if address_intel_service is None:
        # ACS area context is opt-in: set CENSUS_API_KEY (free, email-only key)
        # to enable owner/renter/vacancy context. Absent -> the function still
        # works fully on the keyless geocoder + OSM providers.
        census_api_key = os.environ.get("CENSUS_API_KEY", "").strip()
        area_provider = CensusAcsAreaProvider(census_api_key) if census_api_key else None
        address_intel_service = AddressIntelligenceService(
            CensusGeocoderProvider(),
            dwelling=OverpassDwellingProvider(),
            area=area_provider,
            cache=InMemoryReportCache(),
        )

    # Occupant intelligence: paid WhitePages Pro skip-trace with automatic
    # fallback to the free address layer above. Config toggle via
    # OCCUPANT_PROVIDER ("whitepages" | "census"/"free"); the WhitePages key is
    # read only from the environment (WHITEPAGES_API_KEY, loaded from .env) so it
    # never lives in a committed file. Occupant results persist in a SQLite cache
    # (30-day) for repeat lookups + offline reuse.
    if occupant_intel_service is None:
        occupant_provider_name = _resolve_occupant_provider_name()
        whitepages_api_key = os.environ.get("WHITEPAGES_API_KEY", "").strip()
        whitepages_provider = (
            WhitePagesProProvider(whitepages_api_key)
            if occupant_provider_name == WHITEPAGES_MODE and whitepages_api_key
            else None
        )
        occupant_cache_path = os.environ.get("OCCUPANT_CACHE_PATH", "var/occupant_cache.sqlite").strip()
        occupant_cache = SqliteOccupantCache(occupant_cache_path)
        occupant_cache.purge_expired()  # drop stale entries so the cache file can't grow unbounded
        occupant_intel_service = OccupantLookupService(
            address_intel_service,
            provider=whitepages_provider,
            provider_name=occupant_provider_name,
            cache=occupant_cache,
        )

    api_router = APIRouter()

    @api_router.get("/health", response_model=HealthResponse)
    def get_health(_principal: ApiPrincipalContext = Depends(access_controller.health_access)) -> HealthResponse:
        return build_health_response()

    @api_router.get("/version", response_model=ApiVersionInfo)
    def get_version_info(_principal: ApiPrincipalContext = Depends(access_controller.version_access)) -> ApiVersionInfo:
        return build_version_info()

    @api_router.get("/edge/runtime", response_model=EdgeRuntimeStatus)
    def get_edge_runtime(
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> EdgeRuntimeStatus:
        return edge_runtime_snapshot()

    @api_router.post("/edge/runtime/command", response_model=EdgeRuntimeStatus)
    def command_edge_runtime(
        request: Request,
        submission: EdgeRuntimeCommandSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> EdgeRuntimeStatus:
        current = edge_runtime_snapshot()
        now = _utcnow()
        desired_state = desired_state_for_command(submission.command)
        next_capture_state = (
            EdgeCaptureState.starting
            if submission.command in {EdgeRuntimeCommand.start_capture, EdgeRuntimeCommand.restart_capture}
            else EdgeCaptureState.stopping
            if submission.command == EdgeRuntimeCommand.stop_capture
            else EdgeCaptureState.faulted
            if submission.command == EdgeRuntimeCommand.mark_faulted
            else current.capture_state
        )
        updated = current.model_copy(
            update={
                "capture_state": next_capture_state,
                "desired_capture_state": desired_state,
                "last_command": submission.command,
                "last_commanded_by": submission.operator_id or principal.principal_id,
                "last_commanded_at_utc": now,
                "message": submission.reason or f"Operator command queued: {submission.command.value}",
            }
        )
        updated = update_edge_runtime(updated)
        record_audit(
            request,
            principal=principal,
            action="edge.command",
            outcome=AuditOutcome.success,
            target_type="edge_runtime",
            target_id=updated.edge_node_id,
            details={"command": submission.command.value, "desired_capture_state": desired_state.value},
        )
        return updated

    @api_router.post("/edge/runtime/heartbeat", response_model=EdgeRuntimeStatus)
    def heartbeat_edge_runtime(
        submission: EdgeRuntimeHeartbeatSubmission,
        _principal: ApiPrincipalContext = Depends(access_controller.integrator_access),
    ) -> EdgeRuntimeStatus:
        current = edge_runtime_snapshot()
        updated = current.model_copy(
            update={
                "edge_node_id": submission.edge_node_id,
                "capture_state": submission.capture_state,
                "last_heartbeat_at_utc": _utcnow(),
                "active_camera_count": submission.active_camera_count,
                "total_camera_count": submission.total_camera_count,
                "inference_runtime": submission.inference_runtime or current.inference_runtime,
                "plate_ocr_provider": submission.plate_ocr_provider or current.plate_ocr_provider,
                "vehicle_attribute_provider": submission.vehicle_attribute_provider or current.vehicle_attribute_provider,
                "scan_state": submission.scan_state,
                "scan_processing_mode": submission.scan_processing_mode,
                "primary_ai_camera_id": submission.primary_ai_camera_id or current.primary_ai_camera_id,
                "secondary_context_camera_id": (
                    submission.secondary_context_camera_id or current.secondary_context_camera_id
                ),
                "realtime_lpr_enabled": submission.realtime_lpr_enabled,
                "deferred_vehicle_recognition_enabled": submission.deferred_vehicle_recognition_enabled,
                "message": submission.message or current.message,
            }
        )
        return update_edge_runtime(updated)

    @api_router.get("/dashboard/overview", response_model=DashboardOverview)
    def get_dashboard_overview(
        limit: int = Query(default=20, ge=1, le=100),
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DashboardOverview:
        supporting_limit = max(limit, _DASHBOARD_SUPPORTING_RECORD_LIMIT)
        detections = service.list_detections(limit=limit)
        alerts = service.list_alerts(limit=limit)
        follow_ups = service.list_follow_ups(limit=supporting_limit)
        assignments = service.list_assignments(limit=supporting_limit)
        hotlists = service.list_hotlists(limit=supporting_limit)
        active_alerts = service.list_alerts(status=AlertStatus.active, limit=500)
        active_sessions = service.list_operator_sessions(limit=100)
        camera_health = service.list_camera_health(limit=supporting_limit)
        popup_activity = _build_popup_activity(detections=detections, alerts=alerts, limit=limit)
        return DashboardOverview(
            generated_at_utc=_utcnow(),
            health=build_health_response(),
            camera_health=camera_health,
            counts=DashboardCounts(
                active_alerts=len(active_alerts),
                recent_detections=len(detections),
                active_hotlists=len([record for record in hotlists if record.active]),
                open_follow_ups=len([record for record in follow_ups if record.status != FollowUpStatus.resolved]),
                active_assignments=len(
                    [
                        record
                        for record in assignments
                        if record.status not in {DispatchAssignmentStatus.completed, DispatchAssignmentStatus.cancelled}
                    ]
                ),
                active_sessions=len(active_sessions),
            ),
            detections=detections,
            alerts=alerts,
            follow_ups=follow_ups,
            assignments=assignments,
            hotlists=hotlists,
            popup_activity=popup_activity,
            current_principal=_build_operator_principal(principal),
            active_sessions=active_sessions,
        )

    @api_router.post("/operator/sessions/heartbeat", response_model=OperatorSessionRecord)
    def heartbeat_operator_session(
        submission: OperatorSessionHeartbeatSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> OperatorSessionRecord:
        session = OperatorSessionRecord(
            session_id=submission.session_id,
            principal_id=principal.principal_id,
            display_name=principal.display_name,
            authenticated=principal.authenticated,
            roles=list(principal.roles),
            client_label=submission.client_label,
            workspace=submission.workspace,
            selected_detection_id=submission.selected_detection_id,
            selected_alert_id=submission.selected_alert_id,
            destination_label=submission.destination_label,
            arrival_radius_feet=submission.arrival_radius_feet,
            current_distance_feet=submission.current_distance_feet,
            idle_scan_enabled=submission.idle_scan_enabled,
            visible_map_layers=submission.visible_map_layers,
            navigation_active=submission.navigation_active,
            scan_state=submission.scan_state,
            scan_processing_mode=submission.scan_processing_mode,
            lpr_realtime_enabled=submission.lpr_realtime_enabled,
            vehicle_enrichment_deferred=submission.vehicle_enrichment_deferred,
            primary_ai_camera_id=submission.primary_ai_camera_id,
            secondary_context_camera_id=submission.secondary_context_camera_id,
            last_seen_at_utc=_utcnow(),
        )
        return service.touch_operator_session(session)

    @api_router.get("/search/detections", response_model=DetectionSearchResponse)
    def search_detections(
        request: Request,
        plate: str | None = Query(default=None),
        plate_match: SearchPlateMatchMode = Query(default=SearchPlateMatchMode.contains),
        start_utc: str | None = Query(default=None),
        end_utc: str | None = Query(default=None),
        camera_id: str | None = Query(default=None),
        min_latitude: float | None = Query(default=None),
        max_latitude: float | None = Query(default=None),
        min_longitude: float | None = Query(default=None),
        max_longitude: float | None = Query(default=None),
        geo_shape: GeoShapeType | None = Query(default=None),
        geo_center_latitude: float | None = Query(default=None),
        geo_center_longitude: float | None = Query(default=None),
        geo_radius_meters: float | None = Query(default=None),
        geo_polygon_latitude: list[float] = Query(default_factory=list),
        geo_polygon_longitude: list[float] = Query(default_factory=list),
        vehicle_color: str | None = Query(default=None),
        vehicle_make: str | None = Query(default=None),
        vehicle_model: str | None = Query(default=None),
        vehicle_year: str | None = Query(default=None),
        alert_status: AlertStatus | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DetectionSearchResponse:
        geo_filters = GeoSearchFilters(
            geo_shape=geo_shape,
            geo_center_latitude=geo_center_latitude,
            geo_center_longitude=geo_center_longitude,
            geo_radius_meters=geo_radius_meters,
            geo_polygon_latitude=geo_polygon_latitude,
            geo_polygon_longitude=geo_polygon_longitude,
        )
        geo_kwargs = _geo_search_kwargs(geo_filters)
        results, total = service.search_detections(
            plate_query=plate,
            plate_match_mode=plate_match.value,
            start_timestamp_utc=start_utc,
            end_timestamp_utc=end_utc,
            camera_id=camera_id,
            min_latitude=min_latitude,
            max_latitude=max_latitude,
            min_longitude=min_longitude,
            max_longitude=max_longitude,
            **geo_kwargs,
            vehicle_color=vehicle_color,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            vehicle_year=vehicle_year,
            alert_status=alert_status,
            limit=limit,
            offset=offset,
        )
        record_audit(
            request,
            principal=principal,
            action="search.detections",
            outcome=AuditOutcome.success,
            details={"plate": plate, "camera_id": camera_id, "limit": limit, "offset": offset, "total_results": total},
        )
        return DetectionSearchResponse(page=SearchPageInfo(total_results=total, limit=limit, offset=offset), results=results)

    @api_router.get("/search/alerts", response_model=AlertSearchResponse)
    def search_alerts(
        request: Request,
        plate: str | None = Query(default=None),
        plate_match: SearchPlateMatchMode = Query(default=SearchPlateMatchMode.contains),
        start_utc: str | None = Query(default=None),
        end_utc: str | None = Query(default=None),
        camera_id: str | None = Query(default=None),
        min_latitude: float | None = Query(default=None),
        max_latitude: float | None = Query(default=None),
        min_longitude: float | None = Query(default=None),
        max_longitude: float | None = Query(default=None),
        geo_shape: GeoShapeType | None = Query(default=None),
        geo_center_latitude: float | None = Query(default=None),
        geo_center_longitude: float | None = Query(default=None),
        geo_radius_meters: float | None = Query(default=None),
        geo_polygon_latitude: list[float] = Query(default_factory=list),
        geo_polygon_longitude: list[float] = Query(default_factory=list),
        vehicle_color: str | None = Query(default=None),
        vehicle_make: str | None = Query(default=None),
        vehicle_model: str | None = Query(default=None),
        vehicle_year: str | None = Query(default=None),
        status_filter: AlertStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> AlertSearchResponse:
        geo_filters = GeoSearchFilters(
            geo_shape=geo_shape,
            geo_center_latitude=geo_center_latitude,
            geo_center_longitude=geo_center_longitude,
            geo_radius_meters=geo_radius_meters,
            geo_polygon_latitude=geo_polygon_latitude,
            geo_polygon_longitude=geo_polygon_longitude,
        )
        geo_kwargs = _geo_search_kwargs(geo_filters)
        results, total = service.search_alerts(
            plate_query=plate,
            plate_match_mode=plate_match.value,
            start_timestamp_utc=start_utc,
            end_timestamp_utc=end_utc,
            camera_id=camera_id,
            min_latitude=min_latitude,
            max_latitude=max_latitude,
            min_longitude=min_longitude,
            max_longitude=max_longitude,
            **geo_kwargs,
            vehicle_color=vehicle_color,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            vehicle_year=vehicle_year,
            alert_status=status_filter,
            limit=limit,
            offset=offset,
        )
        record_audit(
            request,
            principal=principal,
            action="search.alerts",
            outcome=AuditOutcome.success,
            details={"plate": plate, "camera_id": camera_id, "limit": limit, "offset": offset, "total_results": total},
        )
        return AlertSearchResponse(page=SearchPageInfo(total_results=total, limit=limit, offset=offset), results=results)

    @api_router.get("/search/addresses", response_model=AddressSearchResponse)
    def search_addresses(
        request: Request,
        query: str = Query(..., alias="q", min_length=3),
        limit: int = Query(default=5, ge=1, le=8),
        bias_latitude: float | None = Query(default=None, ge=-90.0, le=90.0),
        bias_longitude: float | None = Query(default=None, ge=-180.0, le=180.0),
        principal: ApiPrincipalContext = Depends(access_controller.address_search_access),
    ) -> AddressSearchResponse:
        try:
            results = _search_address_candidates(
                query,
                limit=limit,
                bias_latitude=bias_latitude,
                bias_longitude=bias_longitude,
            )
        except AddressSearchProviderError as exc:
            record_audit(
                request,
                principal=principal,
                action="search.addresses",
                outcome=AuditOutcome.error,
                details={
                    "query": query,
                    "limit": limit,
                    "bias_latitude": bias_latitude,
                    "bias_longitude": bias_longitude,
                    "detail": str(exc),
                },
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Address search unavailable") from exc

        record_audit(
            request,
            principal=principal,
            action="search.addresses",
            outcome=AuditOutcome.success,
            details={
                "query": query,
                "limit": limit,
                "bias_latitude": bias_latitude,
                "bias_longitude": bias_longitude,
                "total_results": len(results),
            },
        )
        return AddressSearchResponse(results=results)

    @api_router.get("/search/reverse-address", response_model=ReverseAddressResponse)
    def reverse_address(
        request: Request,
        latitude: float = Query(..., ge=-90.0, le=90.0),
        longitude: float = Query(..., ge=-180.0, le=180.0),
        principal: ApiPrincipalContext = Depends(access_controller.address_search_access),
    ) -> ReverseAddressResponse:
        try:
            result = _reverse_address_lookup(latitude, longitude)
        except AddressSearchProviderError as exc:
            record_audit(
                request,
                principal=principal,
                action="search.reverse_address",
                outcome=AuditOutcome.error,
                details={"latitude": latitude, "longitude": longitude, "detail": str(exc)},
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Reverse address lookup unavailable") from exc

        record_audit(
            request,
            principal=principal,
            action="search.reverse_address",
            outcome=AuditOutcome.success,
            details={"latitude": latitude, "longitude": longitude, "provider": result.provider},
        )
        return result

    @api_router.get("/address-intelligence", response_model=AddressIntelligenceReport)
    def address_intelligence(
        request: Request,
        address: str = Query(..., min_length=3),
        latitude: float | None = Query(default=None, ge=-90.0, le=90.0),
        longitude: float | None = Query(default=None, ge=-180.0, le=180.0),
        principal: ApiPrincipalContext = Depends(access_controller.address_search_access),
    ) -> AddressIntelligenceReport:
        # lookup() is best-effort and never raises — an offline/failed lookup
        # returns an unmatched report with caveats, not a 5xx. Coords (when the
        # UI already resolved the destination) make resolution far more robust.
        report = address_intel_service.lookup(address, latitude=latitude, longitude=longitude)
        record_audit(
            request,
            principal=principal,
            action="address.intelligence",
            outcome=AuditOutcome.success,
            details={
                "address": address,
                "matched": report.matched,
                "dwelling_type": report.dwelling_type.value,
                "sources": report.data_sources,
                "from_cache": report.from_cache,
            },
        )
        return report

    @api_router.get("/occupant-intelligence", response_model=OccupantIntelligenceReport)
    def occupant_intelligence(
        request: Request,
        address: str = Query(..., min_length=3),
        latitude: float | None = Query(default=None, ge=-90.0, le=90.0),
        longitude: float | None = Query(default=None, ge=-180.0, le=180.0),
        address_line_1: str | None = Query(default=None),
        city: str | None = Query(default=None),
        state_code: str | None = Query(default=None),
        postal_code: str | None = Query(default=None),
        case_id: str | None = Query(default=None),
        principal: ApiPrincipalContext = Depends(access_controller.address_search_access),
    ) -> OccupantIntelligenceReport:
        # Optional explicit components override the best-effort address parse.
        components = None
        if any(v for v in (address_line_1, city, state_code, postal_code)):
            components = AddressComponents(
                address_line_1=address_line_1,
                city=city,
                state_code=(state_code or "").upper() or None,
                postal_code=postal_code,
            )

        # Each paid provider call is audited (key already masked by the provider).
        def _audit_provider_call(event) -> None:
            record_audit(
                request,
                principal=principal,
                action="occupant.intelligence.provider_call",
                outcome=AuditOutcome.success if event.success else AuditOutcome.error,
                target_type="occupant_provider",
                target_id=event.endpoint,
                details={
                    "params": event.params_masked,
                    "http_status": event.http_status,
                    "success": event.success,
                    "rate_limited": event.rate_limited,
                    "error": event.error,
                    "case_id": case_id,
                },
            )

        # lookup() is best-effort and never raises — provider failures degrade to
        # the Census address layer (or stale cache) rather than a 5xx.
        report = occupant_intel_service.lookup(
            address,
            latitude=latitude,
            longitude=longitude,
            components=components,
            audit=_audit_provider_call,
        )
        record_audit(
            request,
            principal=principal,
            action="occupant.intelligence",
            outcome=AuditOutcome.success,
            details={
                "address": report.lookup_address,
                "status": report.status.value,
                "source": report.source,
                "occupants": len(report.high_confidence) + len(report.other_possible),
                "from_cache": report.from_cache,
                "case_id": case_id,
            },
        )
        return report

    @api_router.get("/demo/runtime", response_model=DemoRuntimeStatus)
    def get_demo_runtime_status(
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DemoRuntimeStatus:
        return _build_demo_runtime_status(demo_manager.status())

    @api_router.post("/demo/runs", response_model=DemoRuntimeStatus, status_code=status.HTTP_202_ACCEPTED)
    def start_demo_run(
        request: Request,
        submission: DemoRunSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> DemoRuntimeStatus:
        try:
            run_status = demo_manager.start_run(
                frames_directory=submission.frames_directory,
                start_timestamp_utc=submission.start_timestamp_utc,
                frame_interval_ms=submission.frame_interval_ms,
                glob_pattern=submission.glob_pattern,
                start_frame_number=submission.start_frame_number,
                sequence_id=submission.sequence_id,
                plate_text=submission.plate_text,
            )
        except DemoRunInProgressError as exc:
            record_audit(request, principal=principal, action="demo.run.start", outcome=AuditOutcome.rejected, details={"detail": str(exc)})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        record_audit(
            request,
            principal=principal,
            action="demo.run.start",
            outcome=AuditOutcome.success,
            details={"frames_directory": submission.frames_directory, "sequence_id": submission.sequence_id},
        )
        return _build_demo_runtime_status(run_status)

    @api_router.post("/follow-ups", response_model=FollowUpRecord, status_code=status.HTTP_201_CREATED)
    def create_follow_up(
        request: Request,
        submission: FollowUpSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> FollowUpRecord:
        now = _utcnow()
        follow_up = FollowUpRecord(
            follow_up_id=f"fu_{uuid4().hex[:12]}",
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            summary=submission.summary,
            notes=submission.notes,
            due_at_utc=submission.due_at_utc,
            created_at_utc=now,
            updated_at_utc=now,
        )
        try:
            created = service.create_follow_up(follow_up)
        except DetectionNotFoundError as exc:
            record_audit(
                request,
                principal=principal,
                action="follow_up.create",
                outcome=AuditOutcome.rejected,
                target_type="detection",
                target_id=submission.detection_id,
                details={"detail": "Detection not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        record_audit(
            request,
            principal=principal,
            action="follow_up.create",
            outcome=AuditOutcome.success,
            target_type="follow_up",
            target_id=created.follow_up_id,
            details={"detection_id": created.detection_id, "status": created.status.value},
        )
        return created

    @api_router.get("/follow-ups", response_model=list[FollowUpRecord])
    def list_follow_ups(
        detection_id: str | None = Query(default=None),
        status_filter: FollowUpStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[FollowUpRecord]:
        return service.list_follow_ups(detection_id=detection_id, status=status_filter, limit=limit)

    @api_router.get("/follow-ups/{follow_up_id}", response_model=FollowUpRecord)
    def get_follow_up(
        follow_up_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> FollowUpRecord:
        follow_up = service.get_follow_up(follow_up_id)
        if follow_up is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found")
        return follow_up

    @api_router.put("/follow-ups/{follow_up_id}", response_model=FollowUpRecord)
    def update_follow_up(
        request: Request,
        follow_up_id: str,
        submission: FollowUpSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> FollowUpRecord:
        existing = service.get_follow_up(follow_up_id)
        if existing is None:
            record_audit(
                request,
                principal=principal,
                action="follow_up.update",
                outcome=AuditOutcome.rejected,
                target_type="follow_up",
                target_id=follow_up_id,
                details={"detail": "Follow-up not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found")
        follow_up = FollowUpRecord(
            follow_up_id=existing.follow_up_id,
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=existing.created_by_operator_id or principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            summary=submission.summary,
            notes=submission.notes,
            due_at_utc=submission.due_at_utc,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_utcnow(),
        )
        try:
            updated = service.update_follow_up(follow_up)
        except DetectionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        except FollowUpNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found") from exc
        record_audit(
            request,
            principal=principal,
            action="follow_up.update",
            outcome=AuditOutcome.success,
            target_type="follow_up",
            target_id=follow_up_id,
            details={"detection_id": updated.detection_id, "status": updated.status.value},
        )
        return updated

    @api_router.post("/assignments", response_model=DispatchAssignmentRecord, status_code=status.HTTP_201_CREATED)
    def create_assignment(
        request: Request,
        submission: DispatchAssignmentSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> DispatchAssignmentRecord:
        now = _utcnow()
        assignment = DispatchAssignmentRecord(
            assignment_id=f"asg_{uuid4().hex[:12]}",
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            assigned_unit_label=submission.assigned_unit_label,
            destination_label=submission.destination_label,
            summary=submission.summary,
            notes=submission.notes,
            created_at_utc=now,
            updated_at_utc=now,
        )
        try:
            created = service.create_assignment(assignment)
        except DetectionNotFoundError as exc:
            record_audit(
                request,
                principal=principal,
                action="assignment.create",
                outcome=AuditOutcome.rejected,
                target_type="detection",
                target_id=submission.detection_id,
                details={"detail": "Detection not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        except AlertNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from exc
        record_audit(
            request,
            principal=principal,
            action="assignment.create",
            outcome=AuditOutcome.success,
            target_type="assignment",
            target_id=created.assignment_id,
            details={"detection_id": created.detection_id, "status": created.status.value},
        )
        return created

    @api_router.get("/assignments", response_model=list[DispatchAssignmentRecord])
    def list_assignments(
        detection_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[DispatchAssignmentRecord]:
        return service.list_assignments(detection_id=detection_id, limit=limit)

    @api_router.get("/assignments/{assignment_id}", response_model=DispatchAssignmentRecord)
    def get_assignment(
        assignment_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DispatchAssignmentRecord:
        assignment = service.get_assignment(assignment_id)
        if assignment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        return assignment

    @api_router.put("/assignments/{assignment_id}", response_model=DispatchAssignmentRecord)
    def update_assignment(
        request: Request,
        assignment_id: str,
        submission: DispatchAssignmentSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> DispatchAssignmentRecord:
        existing = service.get_assignment(assignment_id)
        if existing is None:
            record_audit(
                request,
                principal=principal,
                action="assignment.update",
                outcome=AuditOutcome.rejected,
                target_type="assignment",
                target_id=assignment_id,
                details={"detail": "Assignment not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        assignment = DispatchAssignmentRecord(
            assignment_id=existing.assignment_id,
            detection_id=submission.detection_id,
            alert_id=submission.alert_id,
            plate_text=submission.plate_text,
            priority=submission.priority,
            status=submission.status,
            created_by_operator_id=existing.created_by_operator_id or principal.principal_id,
            assigned_operator_id=submission.assigned_operator_id,
            assigned_unit_label=submission.assigned_unit_label,
            destination_label=submission.destination_label,
            summary=submission.summary,
            notes=submission.notes,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_utcnow(),
        )
        try:
            updated = service.update_assignment(assignment)
        except DetectionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        except AlertNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from exc
        except AssignmentNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found") from exc
        record_audit(
            request,
            principal=principal,
            action="assignment.update",
            outcome=AuditOutcome.success,
            target_type="assignment",
            target_id=assignment_id,
            details={"detection_id": updated.detection_id, "status": updated.status.value},
        )
        return updated

    @api_router.get("/detections", response_model=list[DetectionRecord])
    def list_detections(
        camera_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[DetectionRecord]:
        return service.list_detections(camera_id=camera_id, limit=limit)

    @api_router.get("/detections/{detection_id}", response_model=DetectionRecord)
    def get_detection(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> DetectionRecord:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        return detection

    @api_router.get("/detections/{detection_id}/frame")
    def get_detection_frame(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> FileResponse:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        media_path = _resolve_media_path(detection.image_path, service.media_layout.root)
        if media_path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame image not found")
        return FileResponse(media_path)

    @api_router.get("/detections/{detection_id}/plate-crop")
    def get_detection_plate_crop(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> FileResponse:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        if not detection.plate_crop_path:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plate crop unavailable")
        media_path = _resolve_media_path(detection.plate_crop_path, service.media_layout.root)
        if media_path is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plate crop unavailable")
        return FileResponse(media_path)

    @api_router.post("/reviews/{detection_id}", response_model=ReviewRecord, status_code=status.HTTP_201_CREATED)
    def create_review(
        request: Request,
        detection_id: str,
        submission: ReviewSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> ReviewRecord:
        review = ReviewRecord(
            review_id=f"rev_{uuid4().hex[:12]}",
            detection_id=detection_id,
            action=submission.action,
            operator_id=submission.operator_id or principal.principal_id,
            corrected_plate_text=submission.corrected_plate_text,
            notes=submission.notes,
            reviewed_at_utc=submission.reviewed_at_utc,
        )
        try:
            created = service.create_review(review)
        except DetectionNotFoundError as exc:
            record_audit(
                request,
                principal=principal,
                action="review.create",
                outcome=AuditOutcome.rejected,
                target_type="detection",
                target_id=detection_id,
                details={"detail": "Detection not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found") from exc
        record_audit(
            request,
            principal=principal,
            action="review.create",
            outcome=AuditOutcome.success,
            target_type="detection",
            target_id=detection_id,
            details={"review_id": created.review_id, "action": created.action.value},
        )
        return created

    @api_router.get("/reviews/{detection_id}", response_model=list[ReviewRecord])
    def list_reviews(
        detection_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[ReviewRecord]:
        detection = service.get_detection(detection_id)
        if detection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
        return service.list_reviews(detection_id)

    @api_router.get("/alerts", response_model=list[AlertRecord])
    def list_alerts(
        camera_id: str | None = Query(default=None),
        status_filter: AlertStatus | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[AlertRecord]:
        return service.list_alerts(camera_id=camera_id, status=status_filter, limit=limit)

    @api_router.get("/alerts/{alert_id}", response_model=AlertRecord)
    def get_alert(
        alert_id: str,
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> AlertRecord:
        alert = service.get_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert

    @api_router.put("/alerts/{alert_id}", response_model=AlertRecord)
    def update_alert(
        request: Request,
        alert_id: str,
        submission: AlertUpdateSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.operator_access),
    ) -> AlertRecord:
        existing = service.get_alert(alert_id)
        if existing is None:
            record_audit(request, principal=principal, action="alert.update", outcome=AuditOutcome.rejected, target_type="alert", target_id=alert_id, details={"detail": "Alert not found"})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        alert = AlertRecord(
            alert_id=existing.alert_id,
            detection_id=existing.detection_id,
            hotlist_entry_id=existing.hotlist_entry_id,
            timestamp_utc=existing.timestamp_utc,
            camera_id=existing.camera_id,
            matched_plate_text=existing.matched_plate_text,
            match_confidence=existing.match_confidence,
            match_type=existing.match_type,
            hotlist_label=existing.hotlist_label,
            notes=existing.notes,
            response_operator_id=submission.operator_id or principal.principal_id,
            response_notes=submission.response_notes,
            updated_at_utc=_utcnow(),
            status=submission.status,
            gps_latitude=existing.gps_latitude,
            gps_longitude=existing.gps_longitude,
        )
        try:
            updated = service.update_alert(alert)
        except AlertNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found") from exc
        record_audit(
            request,
            principal=principal,
            action="alert.update",
            outcome=AuditOutcome.success,
            target_type="alert",
            target_id=alert_id,
            details={"status": updated.status.value, "response_operator_id": updated.response_operator_id},
        )
        return updated

    @api_router.get("/hotlists", response_model=list[HotlistEntry])
    def list_hotlists(
        active_only: bool = Query(default=False),
        limit: int = Query(default=100, ge=1, le=500),
        _principal: ApiPrincipalContext = Depends(access_controller.viewer_access),
    ) -> list[HotlistEntry]:
        return service.list_hotlists(active_only=active_only, limit=limit)

    @api_router.post("/hotlists", response_model=HotlistEntry, status_code=status.HTTP_201_CREATED)
    def create_hotlist(
        request: Request,
        submission: HotlistSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.admin_access),
    ) -> HotlistEntry:
        now = _utcnow()
        entry = HotlistEntry(
            entry_id=f"hl_{uuid4().hex[:12]}",
            plate_text=submission.plate_text,
            vin=submission.vin,
            vehicle_year=submission.vehicle_year,
            vehicle_make=submission.vehicle_make,
            vehicle_model=submission.vehicle_model,
            vehicle_color=submission.vehicle_color,
            address_label=submission.address_label,
            address_line1=submission.address_line1,
            address_line2=submission.address_line2,
            address_city=submission.address_city,
            address_state=submission.address_state,
            address_postal_code=submission.address_postal_code,
            address_latitude=submission.address_latitude,
            address_longitude=submission.address_longitude,
            label=submission.label,
            notes=submission.notes,
            active=submission.active,
            created_at_utc=now,
            updated_at_utc=now,
        )
        created = service.create_hotlist(entry)
        record_audit(
            request,
            principal=principal,
            action="hotlist.create",
            outcome=AuditOutcome.success,
            target_type="hotlist",
            target_id=created.entry_id,
            details={
                "plate_text": created.plate_text,
                "vin": created.vin,
                "vehicle_make": created.vehicle_make,
                "vehicle_model": created.vehicle_model,
                "active": created.active,
            },
        )
        return created

    @api_router.put("/hotlists/{entry_id}", response_model=HotlistEntry)
    def update_hotlist(
        request: Request,
        entry_id: str,
        submission: HotlistSubmission,
        principal: ApiPrincipalContext = Depends(access_controller.admin_access),
    ) -> HotlistEntry:
        existing = service.get_hotlist(entry_id)
        if existing is None:
            record_audit(request, principal=principal, action="hotlist.update", outcome=AuditOutcome.rejected, target_type="hotlist", target_id=entry_id, details={"detail": "Hotlist entry not found"})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found")
        entry = HotlistEntry(
            entry_id=entry_id,
            plate_text=submission.plate_text,
            vin=submission.vin,
            vehicle_year=submission.vehicle_year,
            vehicle_make=submission.vehicle_make,
            vehicle_model=submission.vehicle_model,
            vehicle_color=submission.vehicle_color,
            address_label=submission.address_label,
            address_line1=submission.address_line1,
            address_line2=submission.address_line2,
            address_city=submission.address_city,
            address_state=submission.address_state,
            address_postal_code=submission.address_postal_code,
            address_latitude=submission.address_latitude,
            address_longitude=submission.address_longitude,
            label=submission.label,
            notes=submission.notes,
            active=submission.active,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_utcnow(),
        )
        try:
            updated = service.update_hotlist(entry)
        except HotlistNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found") from exc
        record_audit(
            request,
            principal=principal,
            action="hotlist.update",
            outcome=AuditOutcome.success,
            target_type="hotlist",
            target_id=entry_id,
            details={
                "active": updated.active,
                "label": updated.label,
                "plate_text": updated.plate_text,
                "vin": updated.vin,
                "vehicle_make": updated.vehicle_make,
                "vehicle_model": updated.vehicle_model,
            },
        )
        return updated

    @api_router.delete("/hotlists/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_hotlist(
        request: Request,
        entry_id: str,
        principal: ApiPrincipalContext = Depends(access_controller.admin_access),
    ) -> Response:
        existing = service.get_hotlist(entry_id)
        if existing is None:
            record_audit(
                request,
                principal=principal,
                action="hotlist.delete",
                outcome=AuditOutcome.rejected,
                target_type="hotlist",
                target_id=entry_id,
                details={"detail": "Hotlist entry not found"},
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found")
        try:
            service.delete_hotlist(entry_id)
        except HotlistNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hotlist entry not found") from exc
        record_audit(
            request,
            principal=principal,
            action="hotlist.delete",
            outcome=AuditOutcome.success,
            target_type="hotlist",
            target_id=entry_id,
            details={"plate_text": existing.plate_text},
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @api_router.get("/audit/events", response_model=AuditEventResponse)
    def list_audit_events(
        limit: int = Query(default=100, ge=1, le=500),
        principal_id: str | None = Query(default=None),
        action_prefix: str | None = Query(default=None),
        outcome: AuditOutcome | None = Query(default=None),
        target_id: str | None = Query(default=None),
        _principal: ApiPrincipalContext = Depends(access_controller.audit_access),
    ) -> AuditEventResponse:
        events = audit_logger.list_events(
            limit=limit,
            principal_id=principal_id,
            action_prefix=action_prefix,
            outcome=outcome.value if outcome is not None else None,
            target_id=target_id,
        )
        return AuditEventResponse(events=events)

    canonical_prefix = deployment.api.versioning.canonical_prefix.rstrip("/")
    app.include_router(api_router, prefix=canonical_prefix)
    if deployment.api.versioning.enable_legacy_routes:
        app.include_router(api_router, include_in_schema=False)
    return app
