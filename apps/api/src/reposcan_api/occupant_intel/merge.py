"""Merge two skip-trace providers into one richer result.

Primary (WhitePages) supplies people breadth + current/former classification;
the dates provider (Enformion) supplies per-address residency date ranges. We
enrich the primary occupants' prior addresses with the dates provider's date
ranges (joined by house number + ZIP, which is robust to street-format
differences), and re-order people most-recent-occupancy first.

Best-effort and graceful: if either provider fails, we return the other's
result rather than nothing.
"""

from __future__ import annotations

import re

from reposcan_contracts.occupant_intel import Occupant, PreviousAddress

from .base import AddressComponents, SkipTraceProvider, SkipTraceResult


class MergeProvider(SkipTraceProvider):
    name = "WhitePages + Enformion"

    def __init__(self, primary: SkipTraceProvider, dates: SkipTraceProvider) -> None:
        self._primary = primary  # breadth + is_current (WhitePages)
        self._dates = dates       # per-address date ranges (Enformion)

    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        primary = self._primary.lookup(components)
        dates = self._dates.lookup(components)

        if not primary.ok:
            return dates if dates.ok else primary  # fall through to whichever worked
        if not dates.ok:
            return primary  # graceful: breadth only, no dates

        index = _build_date_index(dates)

        for occupant in (*primary.high_confidence, *primary.other_possible):
            occupant.previous_addresses = [_apply_dates(pa, index) for pa in occupant.previous_addresses]
        primary.previous_addresses = [_apply_dates(pa, index) for pa in primary.previous_addresses]

        # Re-order: current residents first, then most-recent prior occupancy.
        primary.high_confidence.sort(key=_recency_key, reverse=True)
        primary.other_possible.sort(key=_recency_key, reverse=True)

        primary.source = f"{primary.source} + {dates.source}"
        return primary


def _recency_key(occupant: Occupant) -> tuple[bool, str]:
    newest = ""
    for pa in occupant.previous_addresses:
        if pa.date_last_seen and pa.date_last_seen > newest:
            newest = pa.date_last_seen
    return (occupant.is_current, newest)


def _build_date_index(dates: SkipTraceResult) -> dict[tuple[str, str], PreviousAddress]:
    index: dict[tuple[str, str], PreviousAddress] = {}
    pools = [*dates.high_confidence, *dates.other_possible]
    for occupant in pools:
        for pa in occupant.previous_addresses:
            if pa.date_range_label or pa.date_last_seen or pa.date_first_seen:
                index.setdefault(_addr_key(pa.address), pa)
    for pa in dates.previous_addresses:
        if pa.date_range_label or pa.date_last_seen or pa.date_first_seen:
            index.setdefault(_addr_key(pa.address), pa)
    return index


def _apply_dates(pa: PreviousAddress, index: dict[tuple[str, str], PreviousAddress]) -> PreviousAddress:
    # Don't overwrite dates the primary already has.
    if pa.date_range_label or pa.date_last_seen or pa.date_first_seen:
        return pa
    match = index.get(_addr_key(pa.address))
    if match is None:
        return pa
    return pa.model_copy(
        update={
            "date_first_seen": match.date_first_seen,
            "date_last_seen": match.date_last_seen,
            "date_range_label": match.date_range_label,
        }
    )


def _addr_key(address: str) -> tuple[str, str]:
    """Join key robust to street-format differences: (house number, 5-digit ZIP)."""
    number = ""
    m = re.search(r"\d+", address or "")
    if m:
        number = m.group(0)
    zip_ = ""
    z = re.search(r"\b(\d{5})(?:-\d{4})?\b", address or "")
    if z:
        zip_ = z.group(1)
    return number, zip_
