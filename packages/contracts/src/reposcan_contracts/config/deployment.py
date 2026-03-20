"""Deployment profile configuration schema.

Loaded from configs/deployments/*.yaml at service startup.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TargetHardware(str, Enum):
    cpu = "cpu"
    cuda = "cuda"
    jetson_orin = "jetson_orin"
    jetson_xavier = "jetson_xavier"


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


class EnabledServices(BaseModel):
    capture: bool = True
    preprocessing: bool = True
    inference: bool = True
    tracking: bool = True
    storage: bool = True
    alerting: bool = True
    api: bool = True
    ui: bool = True
    sync: bool = False


class InfrastructureConfig(BaseModel):
    postgres_url: str = Field(
        "postgresql://reposcan:reposcan@localhost:5432/reposcan",
        description="PostgreSQL connection string for local metadata storage"
    )
    media_root: str = Field("./media", description="Root path for local media storage")
    api_host: str = Field("127.0.0.1")
    api_port: int = Field(8000, gt=0, le=65535)
    ui_port: int = Field(3000, gt=0, le=65535)
    log_level: LogLevel = LogLevel.info


class MediaRetentionConfig(BaseModel):
    """How long (in days) each media category is kept before pruning."""

    frames_days: int = Field(7, ge=1)
    crops_days: int = Field(30, ge=1)
    snippets_days: int = Field(14, ge=1)
    exports_days: int = Field(90, ge=1)


class PerformanceConfig(BaseModel):
    inference_batch_size: int = Field(1, ge=1, description="Frames per inference batch")
    max_worker_threads: int = Field(4, ge=1)
    frame_queue_depth: int = Field(30, ge=1)
    enable_profiling: bool = False


class DeploymentConfig(BaseModel):
    """Complete deployment profile loaded from configs/deployments/*.yaml."""

    deployment_name: str = Field(..., description="Identifier for this deployment profile")
    description: Optional[str] = None
    target_hardware: TargetHardware = TargetHardware.cpu
    enabled_services: EnabledServices = Field(default_factory=EnabledServices)
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    media_retention: MediaRetentionConfig = Field(default_factory=MediaRetentionConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
