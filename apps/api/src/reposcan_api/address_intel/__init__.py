"""Address intelligence: aggregate zero-cost public data for a destination.

Layering:
  * provider protocols + result types (this package's `providers` module)
  * a pure composition service (`service`) that orchestrates providers into an
    AddressIntelligenceReport, degrading gracefully when a provider is absent,
    offline, or errors
  * concrete keyless HTTP providers (added in a later slice) implement the
    protocols; the service does not care which providers it is given.

The service is fully unit-testable with stub providers — no network required.
"""

from .providers import (
    AreaProvider,
    DwellingProvider,
    DwellingResult,
    GeocodeProvider,
    GeocodeResult,
    ReportCache,
)
from .service import AddressIntelligenceService, InMemoryReportCache, normalize_address_key

__all__ = [
    "AddressIntelligenceService",
    "AreaProvider",
    "DwellingProvider",
    "DwellingResult",
    "GeocodeProvider",
    "GeocodeResult",
    "InMemoryReportCache",
    "ReportCache",
    "normalize_address_key",
]
