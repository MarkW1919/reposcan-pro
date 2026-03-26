"""Deployment profile configuration schema.

Loaded from configs/deployments/*.yaml at service startup.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from .model import ArtifactPathBase, InferenceBackend


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


class MetadataBackend(str, Enum):
    json = "json"
    postgres = "postgres"


class ApiRole(str, Enum):
    viewer = "viewer"
    operator = "operator"
    admin = "admin"
    integrator = "integrator"


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
    metadata_backend: MetadataBackend = Field(
        MetadataBackend.json,
        description="Metadata persistence backend for the storage service",
    )
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


class StoragePressureConfig(BaseModel):
    """Free-space thresholds used by storage maintenance and export workflows."""

    warning_free_space_gb: float = Field(5.0, ge=0.0)
    minimum_free_space_gb: float = Field(2.0, ge=0.0)


class RemoteSyncConfig(BaseModel):
    enabled: bool = False
    endpoint_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float = Field(5.0, gt=0.0)

    @model_validator(mode="after")
    def validate_remote_sync_requirements(self) -> "RemoteSyncConfig":
        if self.enabled and not self.endpoint_url:
            raise ValueError("endpoint_url is required when remote sync is enabled")
        return self


class AlertDeliveryConfig(BaseModel):
    enabled: bool = False
    webhook_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float = Field(5.0, gt=0.0)

    @model_validator(mode="after")
    def validate_alert_delivery_requirements(self) -> "AlertDeliveryConfig":
        if self.enabled and not self.webhook_url:
            raise ValueError("webhook_url is required when alert delivery is enabled")
        return self


class PerformanceConfig(BaseModel):
    inference_batch_size: int = Field(1, ge=1, description="Frames per inference batch")
    max_worker_threads: int = Field(4, ge=1)
    frame_queue_depth: int = Field(30, ge=1)
    enable_profiling: bool = False


class RuntimeCompatibilityConfig(BaseModel):
    required_backend: InferenceBackend | None = Field(
        None,
        description="Required inference backend for this deployment profile.",
    )
    target_runtime: str | None = Field(
        None,
        description="Expected runtime identifier for promoted bundles such as onnxruntime or tensorrt.",
    )
    required_path_base: ArtifactPathBase | None = Field(
        None,
        description="Require a specific path resolution mode for deployment bundles.",
    )
    required_cuda_version: str | None = None
    required_tensorrt_version: str | None = None
    required_compute_capability: str | None = None


class ApiSecurityPrincipal(BaseModel):
    principal_id: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=8)
    roles: list[ApiRole] = Field(default_factory=lambda: [ApiRole.viewer])
    display_name: str | None = None


class ApiSecurityConfig(BaseModel):
    enabled: bool = False
    api_key_header: str = Field("X-RepoScan-Api-Key", min_length=1)
    allow_unauthenticated_health: bool = True
    allow_unauthenticated_version: bool = True
    principals: list[ApiSecurityPrincipal] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_security_requirements(self) -> "ApiSecurityConfig":
        if self.enabled and not self.principals:
            raise ValueError("principals are required when API security is enabled")
        return self


class ApiAuditConfig(BaseModel):
    enabled: bool = True
    log_root: str = Field("./runtime/api-audit", min_length=1)
    max_read_limit: int = Field(500, ge=1, le=5000)


class ApiRateLimitConfig(BaseModel):
    enabled: bool = True
    requests_per_minute: int = Field(240, ge=1, le=100000)


class ApiHardeningConfig(BaseModel):
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "testserver"],
        min_length=1,
    )
    add_security_headers: bool = True
    expose_docs: bool = True


class ApiVersioningConfig(BaseModel):
    current_version: str = Field("v1", min_length=1)
    canonical_prefix: str = Field("/api/v1", min_length=1)
    enable_legacy_routes: bool = True


class ApiConfig(BaseModel):
    security: ApiSecurityConfig = Field(default_factory=ApiSecurityConfig)
    audit: ApiAuditConfig = Field(default_factory=ApiAuditConfig)
    rate_limit: ApiRateLimitConfig = Field(default_factory=ApiRateLimitConfig)
    hardening: ApiHardeningConfig = Field(default_factory=ApiHardeningConfig)
    versioning: ApiVersioningConfig = Field(default_factory=ApiVersioningConfig)


class DeploymentConfig(BaseModel):
    """Complete deployment profile loaded from configs/deployments/*.yaml."""

    deployment_name: str = Field(..., description="Identifier for this deployment profile")
    description: Optional[str] = None
    target_hardware: TargetHardware = TargetHardware.cpu
    enabled_services: EnabledServices = Field(default_factory=EnabledServices)
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    media_retention: MediaRetentionConfig = Field(default_factory=MediaRetentionConfig)
    storage_pressure: StoragePressureConfig = Field(default_factory=StoragePressureConfig)
    remote_sync: RemoteSyncConfig = Field(default_factory=RemoteSyncConfig)
    alert_delivery: AlertDeliveryConfig = Field(default_factory=AlertDeliveryConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    runtime: RuntimeCompatibilityConfig = Field(default_factory=RuntimeCompatibilityConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
