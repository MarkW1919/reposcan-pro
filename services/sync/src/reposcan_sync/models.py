"""Sync queue models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from reposcan_contracts.types import UtcTimestamp


class SyncQueueItem(BaseModel):
    queue_id: str = Field(..., description="Stable queue item identifier")
    record_type: str = Field(..., description="Queued record type, e.g. 'detection'")
    record_id: str = Field(..., description="Identifier of the queued record")
    available_at_utc: UtcTimestamp = Field(..., description="Next time this item is eligible for delivery")
    attempts: int = Field(0, ge=0, description="How many delivery attempts have been made")
    last_error: str | None = Field(None, description="Most recent delivery failure message")


class SyncRunResult(BaseModel):
    synced: int = Field(0, ge=0)
    failed: int = Field(0, ge=0)
    skipped: int = Field(0, ge=0)
