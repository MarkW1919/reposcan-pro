"""Preprocessing service skeleton.

Phase 3 keeps preprocessing intentionally minimal so the pipeline can exercise
service boundaries without inventing image transforms prematurely.
"""

from __future__ import annotations

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import PipelineConfig
from reposcan_contracts.frame import FrameEnvelope


class PreprocessingService:
    def __init__(self, pipeline_config: PipelineConfig) -> None:
        self.pipeline_config = pipeline_config

    @classmethod
    def from_config_path(cls, config_path: str = "configs/pipelines/default-edge.yaml") -> "PreprocessingService":
        return cls(load_pipeline_config(config_path))

    def prepare(self, frame: FrameEnvelope) -> FrameEnvelope:
        return frame
