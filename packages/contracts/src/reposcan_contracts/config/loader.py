"""Configuration loaders.

Each loader reads a YAML file, parses it through the appropriate Pydantic schema,
and raises a clear ConfigLoadError on any validation failure.

Usage:
    from reposcan_contracts.config.loader import load_camera_config
    cam = load_camera_config("configs/cameras/north-gate.yaml")
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from .camera import CameraConfig
from .deployment import DeploymentConfig
from .model import ModelStackConfig
from .pipeline import PipelineConfig
from ..benchmark import PromotedModelBenchmarkManifest
from ..dataset import DatasetSplitManifest, TrainingDatasetManifest
from ..release import ModelReleaseChannel, ModelReleaseRecord
from ..training import TrainingProfileConfig


class ConfigLoadError(Exception):
    """Raised when a config file cannot be parsed or fails Pydantic validation."""

    def __init__(self, path: Union[str, Path], reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"Config load failed for '{self.path}': {reason}")


def _normalize_yaml_scalars(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_yaml_scalars(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_yaml_scalars(item) for key, item in value.items()}
    return value


def _load_yaml(path: Union[str, Path]) -> dict:
    p = Path(path)
    if not p.exists():
        raise ConfigLoadError(p, "file not found")
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(p, f"YAML parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigLoadError(p, "expected a YAML mapping at the top level")
    return _normalize_yaml_scalars(data)


def load_camera_config(path: Union[str, Path]) -> CameraConfig:
    data = _load_yaml(path)
    try:
        return CameraConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_model_config(path: Union[str, Path]) -> ModelStackConfig:
    data = _load_yaml(path)
    try:
        config = ModelStackConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc
    config.set_config_path(path)
    return config


def load_pipeline_config(path: Union[str, Path]) -> PipelineConfig:
    data = _load_yaml(path)
    try:
        return PipelineConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_deployment_config(path: Union[str, Path]) -> DeploymentConfig:
    data = _load_yaml(path)
    try:
        return DeploymentConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_benchmark_manifest(path: Union[str, Path]) -> PromotedModelBenchmarkManifest:
    data = _load_yaml(path)
    try:
        return PromotedModelBenchmarkManifest.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_training_dataset_manifest(path: Union[str, Path]) -> TrainingDatasetManifest:
    data = _load_yaml(path)
    try:
        return TrainingDatasetManifest.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_dataset_split_manifest(path: Union[str, Path]) -> DatasetSplitManifest:
    data = _load_yaml(path)
    try:
        return DatasetSplitManifest.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_training_profile(path: Union[str, Path]) -> TrainingProfileConfig:
    data = _load_yaml(path)
    try:
        return TrainingProfileConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_model_release_record(path: Union[str, Path]) -> ModelReleaseRecord:
    data = _load_yaml(path)
    try:
        return ModelReleaseRecord.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_model_release_channel(path: Union[str, Path]) -> ModelReleaseChannel:
    data = _load_yaml(path)
    try:
        return ModelReleaseChannel.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc
