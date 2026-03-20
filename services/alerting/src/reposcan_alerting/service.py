"""Alerting service skeleton for hotlist evaluation and alert creation."""

from __future__ import annotations

from uuid import uuid4

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import PipelineConfig
from reposcan_contracts.hotlist import HotlistEntry, HotlistMatchResult
from reposcan_contracts.tracking import TrackedDetection
from reposcan_contracts.types import PlateMatchType


def normalize_plate_text(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


class AlertingService:
    def __init__(self, pipeline_config: PipelineConfig) -> None:
        self.pipeline_config = pipeline_config

    @classmethod
    def from_config_path(cls, config_path: str = "configs/pipelines/default-edge.yaml") -> "AlertingService":
        return cls(load_pipeline_config(config_path))

    def match_hotlist(
        self,
        plate_text: str,
        hotlist_entries: list[HotlistEntry],
    ) -> tuple[HotlistMatchResult, HotlistEntry | None]:
        exact_plate = plate_text.strip().upper()
        normalized_plate = normalize_plate_text(plate_text)

        for entry in hotlist_entries:
            if not entry.active:
                continue
            if entry.plate_text == exact_plate:
                return (
                    HotlistMatchResult(
                        matched=True,
                        entry_id=entry.entry_id,
                        match_type=PlateMatchType.exact,
                        plate_text=plate_text,
                    ),
                    entry,
                )

        for entry in hotlist_entries:
            if not entry.active:
                continue
            if normalize_plate_text(entry.plate_text) == normalized_plate:
                return (
                    HotlistMatchResult(
                        matched=True,
                        entry_id=entry.entry_id,
                        match_type=PlateMatchType.normalized,
                        plate_text=plate_text,
                    ),
                    entry,
                )

        return HotlistMatchResult(matched=False, plate_text=plate_text), None

    def evaluate(self, tracked_detection: TrackedDetection, hotlist_entries: list[HotlistEntry]) -> AlertRecord | None:
        best_plate = tracked_detection.best_plate_candidate
        if best_plate is None:
            return None
        if best_plate.confidence < self.pipeline_config.thresholds.alert_min_plate_confidence:
            return None

        match, entry = self.match_hotlist(best_plate.text, hotlist_entries)
        if not match.matched or entry is None:
            return None

        return AlertRecord(
            alert_id=f"alert_{uuid4().hex[:12]}",
            detection_id=tracked_detection.detection_id,
            hotlist_entry_id=entry.entry_id,
            timestamp_utc=tracked_detection.timestamp_utc,
            camera_id=tracked_detection.camera_id,
            matched_plate_text=best_plate.text,
            match_confidence=best_plate.confidence,
            match_type=match.match_type,
            hotlist_label=entry.label,
        )
