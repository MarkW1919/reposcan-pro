"""Accepted release registry helpers for promoted model bundles."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2
import re

import yaml
from pydantic import BaseModel

from reposcan_contracts.benchmark import PromotedModelBenchmarkManifest
from reposcan_contracts.config.deployment import DeploymentConfig
from reposcan_contracts.config.loader import (
    load_benchmark_manifest,
    load_deployment_config,
    load_model_release_channel,
    load_model_release_record,
    load_model_config,
)
from reposcan_contracts.config.model import ClassifierModelConfig, DetectorModelConfig, ModelStackConfig, OcrModelConfig
from reposcan_contracts.model_artifact import ModelArtifactManifest
from reposcan_contracts.release import (
    ModelReleaseChannel,
    ModelReleaseRecord,
    ReleaseBenchmarkSummary,
    ReleaseChannelAction,
    ReleaseChannelEvent,
    ReleaseValidationSummary,
)

from .benchmarking import BenchmarkSubsetMetrics, PromotedModelBenchmarkReport, benchmark_promoted_model
from .deployment_validation import DeploymentCompatibilityReport, validate_deployment_runtime_bundle
from .promotion import load_model_artifact_manifest
from .service import InferenceService

_StageConfig = DetectorModelConfig | OcrModelConfig | ClassifierModelConfig


class ModelReleaseRegistrationReport(BaseModel):
    release_record_path: str
    channel_path: str
    release: ModelReleaseRecord
    channel: ModelReleaseChannel


class ModelReleaseRollbackReport(BaseModel):
    channel_path: str
    channel: ModelReleaseChannel
    active_release: ModelReleaseRecord


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return normalized or "release"


def _write_yaml(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(model.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )


def _stage_entries(model_stack: ModelStackConfig) -> list[tuple[str, _StageConfig]]:
    entries: list[tuple[str, _StageConfig]] = [
        ("vehicle_detector", model_stack.vehicle_detector),
        ("plate_detector", model_stack.plate_detector),
        ("ocr", model_stack.ocr),
    ]
    if model_stack.classifier is not None:
        entries.append(("classifier", model_stack.classifier))
    return entries


def _load_stage_manifests(model_stack: ModelStackConfig) -> list[ModelArtifactManifest]:
    manifests: list[ModelArtifactManifest] = []
    for _, model_config in _stage_entries(model_stack):
        if not model_config.artifact_manifest_path:
            continue
        manifest_path = model_stack.resolve_artifact_path(model_config.artifact_manifest_path)
        if manifest_path.exists():
            manifests.append(load_model_artifact_manifest(manifest_path))
    return manifests


def _unique_nonblank(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return result


def _benchmark_summary(metrics: BenchmarkSubsetMetrics) -> ReleaseBenchmarkSummary:
    return ReleaseBenchmarkSummary(
        frames=metrics.frames,
        exact_match_rate=metrics.exact_match_rate,
        character_accuracy=metrics.character_accuracy,
        color_accuracy=metrics.color_accuracy,
        make_accuracy=metrics.make_accuracy,
    )


def _validation_summary(report: DeploymentCompatibilityReport) -> ReleaseValidationSummary:
    return ReleaseValidationSummary(
        runtime_ready=report.runtime_ready,
        promotion_ready=report.promotion_ready,
        deployment_ready=report.ready,
        error_count=report.error_count,
        warning_count=report.warning_count,
        issues=[issue.message for issue in report.issues],
    )


def _release_paths(registry_root: Path, release_id: str) -> tuple[Path, Path, Path]:
    release_dir = registry_root / "releases" / release_id
    return (
        release_dir,
        release_dir / "release-record.yaml",
        release_dir / "benchmark_report.json",
    )


def _copy_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, destination)


def _default_release_id(channel_name: str, stack_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{_slug(channel_name)}-{_slug(stack_name)}-{stamp}"


def register_model_release(
    *,
    model_config_path: str | Path,
    deployment_config_path: str | Path,
    benchmark_manifest_path: str | Path,
    registry_root: str | Path,
    channel_name: str,
    pipeline_config_path: str | Path = "configs/pipelines/default-edge.yaml",
    release_id: str | None = None,
    notes: str | None = None,
) -> ModelReleaseRegistrationReport:
    model_config_path = Path(model_config_path).resolve()
    deployment_config_path = Path(deployment_config_path).resolve()
    benchmark_manifest_path = Path(benchmark_manifest_path).resolve()
    pipeline_config_path = Path(pipeline_config_path).resolve()
    registry_root = Path(registry_root).resolve()

    model_stack = load_model_config(model_config_path)
    deployment = load_deployment_config(deployment_config_path)
    benchmark_manifest = load_benchmark_manifest(benchmark_manifest_path)
    deployment_report = validate_deployment_runtime_bundle(model_stack, deployment)
    if not deployment_report.ready:
        issue_text = "; ".join(issue.message for issue in deployment_report.issues) or "deployment bundle is not ready"
        raise ValueError(f"cannot register release because deployment validation failed: {issue_text}")

    inference_service = InferenceService.from_config_paths(
        model_config_path=model_config_path,
        pipeline_config_path=pipeline_config_path,
    )
    benchmark_report = benchmark_promoted_model(inference_service, benchmark_manifest)

    final_release_id = release_id or _default_release_id(channel_name, model_stack.stack_name)
    release_dir, release_record_path, benchmark_report_path = _release_paths(registry_root, final_release_id)
    if release_dir.exists():
        raise ValueError(f"release directory already exists: {release_dir}")
    release_dir.mkdir(parents=True, exist_ok=False)

    snapshots_dir = release_dir / "snapshots"
    _copy_snapshot(model_config_path, snapshots_dir / model_config_path.name)
    _copy_snapshot(deployment_config_path, snapshots_dir / deployment_config_path.name)
    _copy_snapshot(benchmark_manifest_path, snapshots_dir / benchmark_manifest_path.name)
    benchmark_report_path.write_text(json.dumps(benchmark_report.model_dump(mode="json"), indent=2), encoding="utf-8")

    channel_path = registry_root / "channels" / f"{_slug(channel_name)}.yaml"
    previous_release_id = None
    existing_channel: ModelReleaseChannel | None = None
    if channel_path.exists():
        existing_channel = load_model_release_channel(channel_path)
        previous_release_id = existing_channel.current_release_id

    stage_manifests = _load_stage_manifests(model_stack)
    release = ModelReleaseRecord(
        release_id=final_release_id,
        channel_name=channel_name,
        released_at_utc=_utcnow(),
        stack_name=model_stack.stack_name,
        bundle_root=str(model_config_path.parent),
        model_config_path=str(model_config_path),
        deployment_config_path=str(deployment_config_path),
        benchmark_manifest_path=str(benchmark_manifest_path),
        benchmark_report_path=str(benchmark_report_path),
        benchmark_name=benchmark_manifest.benchmark_name,
        overall_benchmark=_benchmark_summary(benchmark_report.overall),
        subset_benchmarks={
            name: _benchmark_summary(metrics)
            for name, metrics in benchmark_report.subsets.items()
        },
        validation=_validation_summary(deployment_report),
        source_run_ids=_unique_nonblank([manifest.source_run_id for manifest in stage_manifests]),
        source_checkpoint_refs=_unique_nonblank([manifest.source_checkpoint_ref for manifest in stage_manifests]),
        dataset_manifest_refs=_unique_nonblank(
            [dataset for manifest in stage_manifests for dataset in manifest.dataset_manifests]
        ),
        supersedes_release_id=previous_release_id,
        notes=notes,
    )
    _write_yaml(release_record_path, release)

    release_history = list(existing_channel.release_history) if existing_channel is not None else []
    if final_release_id not in release_history:
        release_history.append(final_release_id)
    events = list(existing_channel.events) if existing_channel is not None else []
    events.append(
        ReleaseChannelEvent(
            occurred_at_utc=release.released_at_utc,
            action=ReleaseChannelAction.promote,
            release_id=final_release_id,
            previous_release_id=previous_release_id,
            notes=notes,
        )
    )
    channel = ModelReleaseChannel(
        channel_name=channel_name,
        current_release_id=final_release_id,
        previous_release_id=previous_release_id,
        updated_at_utc=release.released_at_utc,
        release_history=release_history,
        events=events,
        notes=existing_channel.notes if existing_channel is not None else None,
    )
    _write_yaml(channel_path, channel)

    return ModelReleaseRegistrationReport(
        release_record_path=str(release_record_path),
        channel_path=str(channel_path),
        release=release,
        channel=channel,
    )


def rollback_model_release(
    *,
    registry_root: str | Path,
    channel_name: str,
    target_release_id: str | None = None,
    reason: str | None = None,
) -> ModelReleaseRollbackReport:
    registry_root = Path(registry_root).resolve()
    channel_path = registry_root / "channels" / f"{_slug(channel_name)}.yaml"
    if not channel_path.exists():
        raise ValueError(f"release channel does not exist: {channel_path}")
    channel = load_model_release_channel(channel_path)

    destination_release_id = target_release_id or channel.previous_release_id
    if not destination_release_id:
        raise ValueError("no rollback target is available for this channel")
    if destination_release_id not in channel.release_history:
        raise ValueError(f"release '{destination_release_id}' is not present in channel history")

    release_record_path = registry_root / "releases" / destination_release_id / "release-record.yaml"
    if not release_record_path.exists():
        raise ValueError(f"target release record does not exist: {release_record_path}")
    release = load_model_release_record(release_record_path)

    previous_active = channel.current_release_id
    updated_at = _utcnow()
    channel.events.append(
        ReleaseChannelEvent(
            occurred_at_utc=updated_at,
            action=ReleaseChannelAction.rollback,
            release_id=destination_release_id,
            previous_release_id=previous_active,
            notes=reason,
        )
    )
    channel.previous_release_id = previous_active
    channel.current_release_id = destination_release_id
    channel.updated_at_utc = updated_at
    _write_yaml(channel_path, channel)

    return ModelReleaseRollbackReport(
        channel_path=str(channel_path),
        channel=channel,
        active_release=release,
    )
