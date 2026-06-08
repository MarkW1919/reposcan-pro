"""Occupant lookup coordinator.

Single-provider design with a config toggle and automatic fallback:

  provider = "whitepages"  -> WhitePages Pro occupants + Census address layer.
                              If WhitePages errors/offline, serve stale cache
                              (offline badge) or degrade to the Census address
                              layer alone (status=unavailable) — never a 5xx.
  provider = "census"/"free" -> occupant lookup intentionally off; only the
                              free Census/OSM address verification is returned.

The Census/OSM address verification (``address``) is ALWAYS computed, so a
staged destination always returns useful data regardless of the paid provider's
state. This keeps the existing "enter destination -> intel" workflow intact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from reposcan_contracts.occupant_intel import (
    OCCUPANT_BOUNDARY_CAVEAT,
    Occupant,
    OccupantIntelligenceReport,
    OccupantLookupStatus,
)

from ..address_intel import AddressIntelligenceService
from .base import AddressComponents, SkipTraceAudit, SkipTraceProvider
from .cache import DEFAULT_CACHE_TTL_DAYS, SqliteOccupantCache

# Config values that select the paid occupant provider vs free-only mode.
WHITEPAGES_MODE = "whitepages"
FREE_MODES = {"census", "free", "none", "off"}

AuditHook = Callable[[SkipTraceAudit], None]


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class OccupantLookupService:
    def __init__(
        self,
        address_intel_service: AddressIntelligenceService,
        *,
        provider: Optional[SkipTraceProvider] = None,
        provider_name: str = WHITEPAGES_MODE,
        cache: Optional[SqliteOccupantCache] = None,
        cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
        offline: Callable[[], bool] | None = None,
        clock: Callable[[], str] = _utcnow,
    ) -> None:
        self._address_intel = address_intel_service
        self._provider = provider
        self._mode = (provider_name or WHITEPAGES_MODE).strip().lower()
        self._cache = cache
        self._ttl_days = cache_ttl_days
        self._offline = offline  # optional explicit offline probe (else inferred)
        self._clock = clock

    def lookup(
        self,
        address: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        components: Optional[AddressComponents] = None,
        audit: Optional[AuditHook] = None,
    ) -> OccupantIntelligenceReport:
        comps = components or AddressComponents.parse(address)
        lookup_address = comps.display() or address.strip()
        caveats = [OCCUPANT_BOUNDARY_CAVEAT]

        # Always compute the free address-verification layer (base + fallback).
        address_report = self._address_intel.lookup(address, latitude=latitude, longitude=longitude)

        # Free-only mode (or paid provider not configured): no occupant call.
        if self._mode in FREE_MODES or self._provider is None:
            status = (
                OccupantLookupStatus.unconfigured
                if self._mode == WHITEPAGES_MODE and self._provider is None
                else OccupantLookupStatus.disabled
            )
            if status == OccupantLookupStatus.unconfigured:
                caveats.append(
                    "Occupant lookup provider is not configured "
                    "(set the WhitePages Pro API key to enable people data)."
                )
            return self._report(
                lookup_address,
                status=status,
                source=None,
                address_report=address_report,
                caveats=caveats,
            )

        cache_key = comps.cache_key() or " ".join(address.strip().lower().split())
        cached = self._cache.get(cache_key) if self._cache is not None else None

        # Fresh cache hit -> serve cached occupants (refresh the address layer).
        if cached is not None and cached.is_fresh(self._ttl_days):
            return self._report_from_cache(
                lookup_address,
                cached.payload,
                from_cache=True,
                cache_age_days=cached.age_days,
                status_override=None,
                address_report=address_report,
                caveats=caveats,
            )

        # Live WhitePages call.
        result = self._provider.lookup(comps)
        if audit is not None:
            audit(result.audit)

        if result.ok:
            status = OccupantLookupStatus.ok if result.has_occupants else OccupantLookupStatus.no_match
            payload = _occupants_to_payload(
                status=status,
                source=result.source,
                high_confidence=result.high_confidence,
                other_possible=result.other_possible,
                previous_addresses=result.previous_addresses,
            )
            # Cache positive matches only. "No record at this address" is not
            # stable skip-trace data (subject may move in, records update), so a
            # 30-day no_match cache would mask later hits — re-query next time.
            if self._cache is not None and status == OccupantLookupStatus.ok:
                self._cache.put(cache_key, payload)
            if status == OccupantLookupStatus.no_match:
                caveats.append("No occupant records were returned for this address.")
            return self._report(
                lookup_address,
                status=status,
                source=result.source,
                high_confidence=result.high_confidence,
                other_possible=result.other_possible,
                previous_addresses=result.previous_addresses,
                address_report=address_report,
                caveats=caveats,
            )

        # Provider failed/offline/rate-limited -> serve stale cache if we have it.
        if cached is not None:
            offline_caveat = f"Occupant data shown from cache (last updated {cached.fetched_at.date().isoformat()})."
            return self._report_from_cache(
                lookup_address,
                cached.payload,
                from_cache=True,
                cache_age_days=cached.age_days,
                status_override=OccupantLookupStatus.offline,
                address_report=address_report,
                caveats=caveats + [offline_caveat],
            )

        # No cache and provider unavailable.
        if result.audit.rate_limited:
            caveats.append("Occupant lookup is rate-limited right now — try again shortly.")
        else:
            caveats.append("Occupant lookup is currently unavailable (provider offline) — showing address verification only.")
        return self._report(
            lookup_address,
            status=OccupantLookupStatus.unavailable,
            source=result.source,
            address_report=address_report,
            caveats=caveats,
        )

    # ---- builders -------------------------------------------------------

    def _report(
        self,
        lookup_address: str,
        *,
        status: OccupantLookupStatus,
        source: Optional[str],
        address_report,
        caveats: list[str],
        high_confidence: Optional[list[Occupant]] = None,
        other_possible: Optional[list[Occupant]] = None,
        previous_addresses: Optional[list[str]] = None,
        from_cache: bool = False,
        cache_age_days: Optional[int] = None,
    ) -> OccupantIntelligenceReport:
        return OccupantIntelligenceReport(
            lookup_address=lookup_address,
            generated_at_utc=self._clock(),
            status=status,
            source=source,
            high_confidence=high_confidence or [],
            other_possible=other_possible or [],
            previous_addresses=previous_addresses or [],
            from_cache=from_cache,
            cache_age_days=cache_age_days,
            address=address_report,
            caveats=caveats,
        )

    def _report_from_cache(
        self,
        lookup_address: str,
        payload: dict,
        *,
        from_cache: bool,
        cache_age_days: Optional[int],
        status_override: Optional[OccupantLookupStatus],
        address_report,
        caveats: list[str],
    ) -> OccupantIntelligenceReport:
        high_confidence, other_possible, previous, cached_status, source = _occupants_from_payload(payload)
        status = status_override or cached_status
        return self._report(
            lookup_address,
            status=status,
            source=source,
            high_confidence=high_confidence,
            other_possible=other_possible,
            previous_addresses=previous,
            address_report=address_report,
            caveats=caveats,
            from_cache=from_cache,
            cache_age_days=cache_age_days,
        )


def _occupants_to_payload(
    *,
    status: OccupantLookupStatus,
    source: str,
    high_confidence: list[Occupant],
    other_possible: list[Occupant],
    previous_addresses: list[str],
) -> dict:
    return {
        "status": status.value,
        "source": source,
        "high_confidence": [o.model_dump() for o in high_confidence],
        "other_possible": [o.model_dump() for o in other_possible],
        "previous_addresses": list(previous_addresses),
    }


def _occupants_from_payload(
    payload: dict,
) -> tuple[list[Occupant], list[Occupant], list[str], OccupantLookupStatus, Optional[str]]:
    def _people(items: object) -> list[Occupant]:
        out: list[Occupant] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    try:
                        # model_validate tolerates extra/missing fields across
                        # cache-schema evolution rather than dropping the entry.
                        out.append(Occupant.model_validate(item))
                    except (TypeError, ValueError):
                        continue
        return out

    try:
        cached_status = OccupantLookupStatus(payload.get("status", OccupantLookupStatus.ok.value))
    except ValueError:
        cached_status = OccupantLookupStatus.ok
    previous = payload.get("previous_addresses")
    return (
        _people(payload.get("high_confidence")),
        _people(payload.get("other_possible")),
        [str(a) for a in previous] if isinstance(previous, list) else [],
        cached_status,
        payload.get("source"),
    )
