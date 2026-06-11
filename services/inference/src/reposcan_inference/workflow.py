"""Workflow helpers for the Phase 3 frame-to-candidate path."""

from __future__ import annotations

from typing import Iterable

from reposcan_contracts.frame import FrameEnvelope, PreparedFrame
from reposcan_contracts.inference import InferenceCandidate
from reposcan_preprocessing import PreprocessingService

from .service import InferenceService


class FrameToCandidateWorkflow:
    def __init__(
        self,
        *,
        inference_service: InferenceService,
        preprocessing_service: PreprocessingService | None = None,
    ) -> None:
        self.inference_service = inference_service
        self.preprocessing_service = preprocessing_service

    def process(self, frame: FrameEnvelope) -> InferenceCandidate:
        prepared: FrameEnvelope | PreparedFrame = frame
        if self.preprocessing_service is not None:
            prepared = self.preprocessing_service.prepare(frame)
        return self.inference_service.run(prepared)

    def process_many(self, frames: Iterable[FrameEnvelope]) -> list[InferenceCandidate]:
        return [self.process(frame) for frame in frames]
