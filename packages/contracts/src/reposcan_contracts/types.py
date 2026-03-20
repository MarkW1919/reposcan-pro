"""Shared contract types and validators."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator


def _validate_utc_timestamp(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("timestamp must not be blank")

    candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("timestamp must be a valid ISO 8601 datetime") from exc

    offset = parsed.utcoffset()
    if offset is None:
        raise ValueError("timestamp must include timezone information")
    if offset != timedelta(0):
        raise ValueError("timestamp must be expressed in UTC")

    return normalized


UtcTimestamp = Annotated[str, AfterValidator(_validate_utc_timestamp)]


class PlateMatchType(str, Enum):
    exact = "exact"
    normalized = "normalized"
