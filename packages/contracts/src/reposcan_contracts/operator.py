"""Operator identity and presence contracts."""

from __future__ import annotations

from enum import Enum
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
    can_control_edge_runtime: bool = False
    can_view_audit: bool = False


class OperatorPrincipal(BaseModel):
    principal_id: str = Field(..., min_length=1)
    display_name: Optional[str] = None
    authenticated: bool = False
    roles: list[ApiRole] = Field(default_factory=list)
    capabilities: OperatorCapabilities = Field(default_factory=OperatorCapabilities)


class ScanSessionState(str, Enum):
    idle = "idle"
    approaching_radius = "approaching_radius"
    active_lpr_scan = "active_lpr_scan"
    post_scan_vehicle_enrichment = "post_scan_vehicle_enrichment"
    completed = "completed"


class ScanProcessingMode(str, Enum):
    standby = "standby"
    realtime_lpr = "realtime_lpr"
    deferred_vehicle_recognition = "deferred_vehicle_recognition"


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
    destination_label: Optional[str] = None
    arrival_radius_feet: Optional[int] = Field(None, ge=1)
    current_distance_feet: Optional[float] = Field(None, ge=0.0)
    idle_scan_enabled: bool = False
    visible_map_layers: list[str] = Field(default_factory=list)
    navigation_active: bool = False
    scan_state: ScanSessionState = ScanSessionState.idle
    scan_processing_mode: ScanProcessingMode = ScanProcessingMode.standby
    lpr_realtime_enabled: bool = False
    vehicle_enrichment_deferred: bool = True
    primary_ai_camera_id: Optional[str] = None
    secondary_context_camera_id: Optional[str] = None
    last_seen_at_utc: UtcTimestamp
