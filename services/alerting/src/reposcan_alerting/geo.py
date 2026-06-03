"""Geofence helpers for in-zone hotlist matching.

A make/model lead only fires when the unit is inside the configured radius of
a hotlist entry's target address. These helpers compute that membership from
the unit's current GPS position; they are pure (no I/O) and unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import asin, cos, radians, sin, sqrt

from reposcan_contracts.hotlist import HotlistEntry

# Mean Earth radius in feet (matches the unit used by arrival-radius settings).
_EARTH_RADIUS_FEET = 20_902_231.0


def haversine_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in feet."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    half_chord = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_FEET * asin(min(1.0, sqrt(half_chord)))


def entries_within_zone(
    unit_latitude: float,
    unit_longitude: float,
    entries: Iterable[HotlistEntry],
    radius_feet: float,
) -> set[str]:
    """Return the ids of active entries whose target address is within radius.

    Entries without address coordinates are excluded (no geofence to test).
    """
    in_zone: set[str] = set()
    for entry in entries:
        if not entry.active:
            continue
        if entry.address_latitude is None or entry.address_longitude is None:
            continue
        distance = haversine_feet(
            unit_latitude, unit_longitude, entry.address_latitude, entry.address_longitude
        )
        if distance <= radius_feet:
            in_zone.add(entry.entry_id)
    return in_zone
