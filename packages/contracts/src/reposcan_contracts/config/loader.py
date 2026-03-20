"""Configuration loaders.

Each loader reads a YAML file, parses it through the appropriate Pydantic schema,
and raises a clear ConfigLoadError on any validation failure.

Usage:
    from reposcan_contracts.config.loader import load_camera_config
    cam = load_camera_config("configs/cameras/north-gate.yaml")
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from .camera import CameraConfig
from .deployment import DeploymentConfig
from .model import ModelStackConfig
from .pipeline import PipelineConfig


class ConfigLoadError(Exception):
    """Raised when a config file cannot be parsed or fails Pydantic validation."""

    def __init__(self, path: Union[str, Path], reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"Config load failed for '{self.path}': {reason}")


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
    return data


def load_camera_config(path: Union[str, Path]) -> CameraConfig:
    data = _load_yaml(path)
    try:
        return CameraConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


def load_model_config(path: Union[str, Path]) -> ModelStackConfig:
    data = _load_yaml(path)
    try:
        return ModelStackConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(path, str(exc)) from exc


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
