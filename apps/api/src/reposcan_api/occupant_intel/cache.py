"""SQLite-backed occupant cache (30-day expiry + offline reuse).

Persists the occupant portion of a lookup so repeat lookups are instant and so
the operator can serve last-known data while offline (the spec's "offline –
last updated [date]" badge). Stdlib sqlite3 only — no new dependency, aligned
with the edge-first mandate.

Only the occupant data is cached here (names/phones/associates/previous
addresses + source/status); the address-verification layer has its own cache
and is always recomputed live so it reflects current map/area data.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Optional

DEFAULT_CACHE_TTL_DAYS = 30


@dataclass
class OccupantCacheEntry:
    payload: dict
    fetched_at: datetime
    age_days: int

    def is_fresh(self, ttl_days: int = DEFAULT_CACHE_TTL_DAYS) -> bool:
        return self.age_days <= ttl_days


class SqliteOccupantCache:
    """Thread-safe single-connection SQLite cache for occupant payloads."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + a lock: safe for the local edge API's threads.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._lock = RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS occupant_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at_utc TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def get(self, key: str, *, now: Optional[datetime] = None) -> Optional[OccupantCacheEntry]:
        now = now or datetime.now(timezone.utc)
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT payload, fetched_at_utc FROM occupant_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
        except sqlite3.Error:
            return None  # corrupt/locked DB -> treat as a cache miss, never crash
        if row is None:
            return None
        payload_text, fetched_text = row
        try:
            payload = json.loads(payload_text)
            fetched_at = _parse_utc(fetched_text)
        except (ValueError, TypeError):
            return None
        age_days = max(0, (now - fetched_at).days)
        return OccupantCacheEntry(payload=payload, fetched_at=fetched_at, age_days=age_days)

    def put(self, key: str, payload: dict, *, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO occupant_cache (cache_key, payload, fetched_at_utc)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload = excluded.payload,
                        fetched_at_utc = excluded.fetched_at_utc
                    """,
                    (key, json.dumps(payload), _to_utc_text(now)),
                )
                self._conn.commit()
        except sqlite3.Error:
            pass  # non-fatal: just a cache miss next time

    def purge_expired(self, *, ttl_days: int = DEFAULT_CACHE_TTL_DAYS, now: Optional[datetime] = None) -> int:
        now = now or datetime.now(timezone.utc)
        cutoff = _to_utc_text(now.replace(microsecond=0))
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "DELETE FROM occupant_cache WHERE julianday(?) - julianday(fetched_at_utc) > ?",
                    (cutoff, ttl_days),
                )
                self._conn.commit()
                return cursor.rowcount
        except sqlite3.Error:
            return 0

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.close()
        except sqlite3.Error:
            pass


def _to_utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(text: str) -> datetime:
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
