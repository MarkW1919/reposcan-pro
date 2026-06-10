"""Merge two skip-trace providers into one richer result.

Strategy (Enformion-primary union): Enformion natively returns every person with
their FULL dated address history + current/former, so it is the base for the
occupant list — that maximizes per-address date coverage (the field must-have).
WhitePages then fills gaps: phone numbers (Enformion sometimes returns none),
extra relatives, and any people Enformion didn't return (added as "other
possible", with dates applied by address where we have them).

Best-effort and graceful: if the dated provider fails we fall back to the
breadth provider alone (no dates); if breadth fails we use the dated provider
alone.
"""

from __future__ import annotations

import re

from reposcan_contracts.occupant_intel import Occupant, PreviousAddress

from .base import AddressComponents, SkipTraceProvider, SkipTraceResult


class MergeProvider(SkipTraceProvider):
    name = "WhitePages + Enformion"

    def __init__(self, breadth: SkipTraceProvider, dated: SkipTraceProvider) -> None:
        self._breadth = breadth  # WhitePages: phones/relatives breadth
        self._dated = dated       # Enformion: per-address date ranges (the base)

    def lookup(self, components: AddressComponents) -> SkipTraceResult:
        breadth = self._breadth.lookup(components)
        dated = self._dated.lookup(components)

        if not dated.ok:
            return breadth  # no dates available -> breadth alone (graceful)
        if not breadth.ok:
            return dated  # fully dated, no breadth fill

        wp_by_name = {_norm_name(o.name): o for o in (*breadth.high_confidence, *breadth.other_possible)}
        date_index = _build_date_index(dated)

        # Base occupants = Enformion (already fully dated); fill phones/relatives.
        base = [*dated.high_confidence, *dated.other_possible]
        for occ in base:
            wp = wp_by_name.get(_norm_name(occ.name))
            if wp is not None:
                if not occ.phones and wp.phones:
                    occ.phones = list(wp.phones)
                occ.associated_people = _union(occ.associated_people, wp.associated_people)

        # Add WhitePages-only people (not returned by Enformion), dated by address.
        en_names = {_norm_name(o.name) for o in base}
        extras: list[Occupant] = []
        for occ in (*breadth.high_confidence, *breadth.other_possible):
            if _norm_name(occ.name) in en_names:
                continue
            occ.previous_addresses = [_apply_dates(pa, date_index) for pa in occ.previous_addresses]
            extras.append(occ)

        people = base + extras
        people.sort(key=_recency_key, reverse=True)
        current = [o for o in people if o.is_current]
        rest = [o for o in people if not o.is_current]
        high = (current + rest)[:6]
        other = (current + rest)[6:12]

        return SkipTraceResult(
            source=f"{breadth.source} + {dated.source}",
            ok=True,
            high_confidence=high,
            other_possible=other,
            previous_addresses=dated.previous_addresses or breadth.previous_addresses,
            audit=dated.audit,
        )


def _recency_key(occupant: Occupant) -> tuple[bool, str]:
    newest = ""
    for pa in occupant.previous_addresses:
        if pa.date_last_seen and pa.date_last_seen > newest:
            newest = pa.date_last_seen
    return (occupant.is_current, newest)


def _union(primary: list[str], extra: list[str]) -> list[str]:
    out = list(primary)
    seen = {x.lower() for x in out}
    for item in extra:
        if item.lower() not in seen:
            out.append(item)
            seen.add(item.lower())
    return out[:8]


def _build_date_index(dated: SkipTraceResult) -> dict[tuple[str, str], PreviousAddress]:
    index: dict[tuple[str, str], PreviousAddress] = {}
    for occupant in (*dated.high_confidence, *dated.other_possible):
        for pa in occupant.previous_addresses:
            if pa.date_range_label or pa.date_last_seen or pa.date_first_seen:
                index.setdefault(_addr_key(pa.address), pa)
    for pa in dated.previous_addresses:
        if pa.date_range_label or pa.date_last_seen or pa.date_first_seen:
            index.setdefault(_addr_key(pa.address), pa)
    return index


def _apply_dates(pa: PreviousAddress, index: dict[tuple[str, str], PreviousAddress]) -> PreviousAddress:
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


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def _addr_key(address: str) -> tuple[str, str]:
    number = ""
    m = re.search(r"\d+", address or "")
    if m:
        number = m.group(0)
    zip_ = ""
    z = re.search(r"\b(\d{5})(?:-\d{4})?\b", address or "")
    if z:
        zip_ = z.group(1)
    return number, zip_
