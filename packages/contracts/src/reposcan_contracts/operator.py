"""Operator identity and presence contracts."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .config.deployment import ApiRole
from .types import UtcTimestamp


class OperatorCapabilities(BaseModel):
    can_submit_reviews: bool = False
    can_update_alerts: bool = False
    can_manage_hotlists: bool = False
    can_manage_follow_ups: bool = False
    can_manage_dispatch: bool = False
    can_start_demo_runs: bool = False
    can_view_audit: bool = False


class OperatorPrincipal(BaseModel):
    principal_id: str = Field(..., min_length=1)
    display_name: Optional[str] = None
    authenticated: bool = False
    roles: list[ApiRole] = Field(default_factory=list)
    capabilities: OperatorCapabilities = Field(default_factory=OperatorCapabilities)


class OperatorSessionRecord(BaseModel):
    session_id: str = Field(..., min_length=1)
    principal_id: str = Field(..., min_length=1)
    display_name: Optional[str] = None
    authenticated: bool = False
    roles: list[ApiRole] = Field(default_factory=list)
    client_label: Optional[str] = None
    workspace: str = Field(..., min_length=1)
    selected_detection_id: Optional[str] = Field(None, min_length=1)
    selected_alert_id: Optional[str] = Field(None, min_length=1)
    navigation_active: bool = False
    last_seen_at_utc: UtcTimestamp
