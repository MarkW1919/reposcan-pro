"""Occupant intelligence: who is associated with a staged destination.

Layering mirrors address_intel:
  * a skip-trace provider ABC + value types (`base`)
  * a paid WhitePages Pro provider (`whitepages_pro`) implementing the ABC
  * a SQLite 30-day cache (`cache`) for repeat lookups + offline reuse
  * a coordinator (`lookup_service`) with a config toggle (whitepages | free)
    that always returns the free Census/OSM address layer and falls back to it
    when the paid provider is unavailable.

Fully unit-testable with an injected HTTP transport — no network required.
"""

from .base import (
    AddressComponents,
    SkipTraceAudit,
    SkipTraceProvider,
    SkipTraceResult,
)
from .cache import DEFAULT_CACHE_TTL_DAYS, OccupantCacheEntry, SqliteOccupantCache
from .enformion_pro import (
    ENFORMION_PERSON_SEARCH_URL,
    EnformionProvider,
    EnformionTransport,
    UrllibEnformionTransport,
)
from .lookup_service import FREE_MODES, WHITEPAGES_MODE, OccupantLookupService
from .merge import MergeProvider
from .whitepages_pro import (
    WHITEPAGES_PERSON_URL,
    HttpJsonResponse,
    HttpTransport,
    UrllibTransport,
    WhitePagesProProvider,
)

__all__ = [
    "AddressComponents",
    "DEFAULT_CACHE_TTL_DAYS",
    "ENFORMION_PERSON_SEARCH_URL",
    "EnformionProvider",
    "EnformionTransport",
    "FREE_MODES",
    "HttpJsonResponse",
    "HttpTransport",
    "MergeProvider",
    "OccupantCacheEntry",
    "OccupantLookupService",
    "SkipTraceAudit",
    "SkipTraceProvider",
    "SkipTraceResult",
    "SqliteOccupantCache",
    "UrllibEnformionTransport",
    "UrllibTransport",
    "WHITEPAGES_PERSON_URL",
    "WHITEPAGES_MODE",
    "WhitePagesProProvider",
]
