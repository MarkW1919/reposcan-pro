"""Health contract — response shape for GET /health.

Each service exposes a health endpoint.  The API aggregates dependency statuses
from downstream services into a single HealthResponse.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .types import UtcTimestamp


class HealthState(str, Enum):
    ok = "ok"
    degraded = "degraded"
    down = "down"


class DependencyHealth(BaseModel):
    """Health status of a single named dependency (database, model runtime, etc.)."""

    name: str = Field(..., description="Dependency name, e.g. 'postgres' or 'inference-service'")
    state: HealthState = Field(..., description="Current state of this dependency")
    latency_ms: Optional[float] = Field(None, ge=0.0, description="Round-trip probe latency when available")
    message: Optional[str] = Field(None, description="Human-readable status message or error detail")


class CameraHealthStatus(str, Enum):
    online = "online"
    offline = "offline"
    unknown = "unknown"


class CameraHealthRecord(BaseModel):
    """Derived health view for a single known camera feed."""

    camera_id: str = Field(..., description="Stable logical camera identifier")
    label: str = Field(..., description="Human-readable camera label")
    status: CameraHealthStatus = Field(..., description="Derived camera availability state")
    last_seen_at_utc: Optional[UtcTimestamp] = Field(
        None,
        description="UTC timestamp of the most recent detection seen for this camera",
    )
    fps: Optional[float] = Field(None, gt=0.0, description="Configured or observed camera frame rate")


class HealthResponse(BaseModel):
    """Response body for GET /health.

    Overall state is the worst state of any dependency.  Services that are
    fully isolated (no dependencies) report ok directly.
    """

    service: str = Field(..., description="Name of the service reporting health")
    version: str = Field(..., description="Service version string")
    state: HealthState = Field(..., description="Overall health state")
    timestamp_utc: UtcTimestamp = Field(..., description="UTC timestamp of this health snapshot (ISO 8601)")
    dependencies: list[DependencyHealth] = Field(
        default_factory=list, description="Per-dependency health breakdown"
    )
    uptime_seconds: Optional[float] = Field(None, ge=0.0, description="Seconds since service start")
