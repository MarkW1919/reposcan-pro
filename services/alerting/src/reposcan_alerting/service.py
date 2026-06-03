"""Alerting service skeleton for hotlist evaluation and alert creation."""

from __future__ import annotations

from uuid import uuid4

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import PipelineConfig
from reposcan_contracts.hotlist import HotlistEntry, HotlistMatchResult
from reposcan_contracts.inference import AttributePredictions
from reposcan_contracts.tracking import TrackedDetection
from reposcan_contracts.types import HotlistMatchKind, PlateMatchType

# Geofenced make/model lead scoring. make+model is the required floor (0.6);
# color and year each refine the confidence shown to the driver.
_PROFILE_BASE_SCORE = 0.6
_PROFILE_COLOR_BONUS = 0.2
_PROFILE_YEAR_BONUS = 0.2


def normalize_plate_text(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.strip().lower().split())
    return collapsed or None


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
        """Match a detected plate against active hotlist entries.

        IMPORTANT — matching is plate-only by design. ``HotlistEntry`` also
        allows VIN-only and vehicle-profile-only (make+model) entries, but:
          * VINs are not observable from an LPR camera (it reads plates, not
            the dash/door VIN), so VIN entries can never fire from detections;
          * make/model-only matching against classifier attributes would be a
            false-positive firehose (every white Camry would alert).
        Such entries are therefore stored as operator reference/context and do
        NOT trigger live alerts here. This is a deliberate product boundary, not
        an oversight — surfacing make/model BOLO alerts (with confidence/dedup
        handling) is a future feature decision, tracked in the pipeline status
        doc. Entries without a plate_text are skipped below.
        """
        exact_plate = plate_text.strip().upper()
        normalized_plate = normalize_plate_text(plate_text)

        for entry in hotlist_entries:
            if not entry.active:
                continue
            if not entry.plate_text:
                continue
            if entry.plate_text == exact_plate:
                return (
                    HotlistMatchResult(
                        matched=True,
                        entry_id=entry.entry_id,
                        match_kind=HotlistMatchKind.plate,
                        match_type=PlateMatchType.exact,
                        score=1.0,
                        matched_dimensions=["plate"],
                        plate_text=plate_text,
                    ),
                    entry,
                )

        for entry in hotlist_entries:
            if not entry.active:
                continue
            if not entry.plate_text:
                continue
            if normalize_plate_text(entry.plate_text) == normalized_plate:
                return (
                    HotlistMatchResult(
                        matched=True,
                        entry_id=entry.entry_id,
                        match_kind=HotlistMatchKind.plate,
                        match_type=PlateMatchType.normalized,
                        score=0.9,
                        matched_dimensions=["plate"],
                        plate_text=plate_text,
                    ),
                    entry,
                )

        return HotlistMatchResult(matched=False, plate_text=plate_text), None

    def match_profile_in_zone(
        self,
        attributes: AttributePredictions | None,
        hotlist_entries: list[HotlistEntry],
        in_zone_entry_ids: set[str],
    ) -> tuple[HotlistMatchResult, HotlistEntry | None]:
        """Match a detected vehicle's make/model against in-zone hotlist targets.

        Only entries in ``in_zone_entry_ids`` (within the configured radius of
        their address) are considered. make AND model must both match (the
        configured floor); color and year refine the score. This is the
        geofenced IN-ZONE LEAD path for plate-unknown / plate-switched recoveries.
        """
        no_match = HotlistMatchResult(matched=False, plate_text="")
        if attributes is None:
            return no_match, None
        det_make = _norm(attributes.make)
        det_model = _norm(attributes.model_label)
        if det_make is None or det_model is None:
            return no_match, None

        best: tuple[float, list[str], HotlistEntry] | None = None
        for entry in hotlist_entries:
            if not entry.active or entry.entry_id not in in_zone_entry_ids:
                continue
            target_make = _norm(entry.vehicle_make)
            target_model = _norm(entry.vehicle_model)
            if target_make is None or target_model is None:
                continue
            if det_make != target_make or det_model != target_model:
                continue

            dimensions = ["make", "model"]
            score = _PROFILE_BASE_SCORE
            det_color = _norm(attributes.color)
            if det_color is not None and det_color == _norm(entry.vehicle_color):
                score += _PROFILE_COLOR_BONUS
                dimensions.append("color")
            det_year = _norm(attributes.year)
            if det_year is not None and det_year == _norm(entry.vehicle_year):
                score += _PROFILE_YEAR_BONUS
                dimensions.append("year")

            if best is None or score > best[0]:
                best = (min(score, 1.0), dimensions, entry)

        if best is None:
            return no_match, None
        score, dimensions, entry = best
        return (
            HotlistMatchResult(
                matched=True,
                entry_id=entry.entry_id,
                match_kind=HotlistMatchKind.in_zone_profile,
                score=score,
                matched_dimensions=dimensions,
                plate_text="",
            ),
            entry,
        )

    def evaluate(
        self,
        tracked_detection: TrackedDetection,
        hotlist_entries: list[HotlistEntry],
        *,
        in_zone_entry_ids: set[str] | None = None,
    ) -> AlertRecord | None:
        """Produce an alert for a detection, if it matches the hotlist.

        Plate matches (CONFIRMED) fire anywhere and take priority. When
        ``in_zone_entry_ids`` is supplied (entries within the configured radius
        of their address — see ``entries_within_zone``), a make/model match
        against those targets fires an IN-ZONE LEAD even with no plate match.
        Backward compatible: omit ``in_zone_entry_ids`` for plate-only behavior.
        """
        best_plate = tracked_detection.best_plate_candidate

        # CONFIRMED: plate match anywhere (highest priority).
        if best_plate is not None and best_plate.confidence >= self.pipeline_config.thresholds.alert_min_plate_confidence:
            match, entry = self.match_hotlist(best_plate.text, hotlist_entries)
            if match.matched and entry is not None:
                return AlertRecord(
                    alert_id=f"alert_{uuid4().hex[:12]}",
                    detection_id=tracked_detection.detection_id,
                    hotlist_entry_id=entry.entry_id,
                    timestamp_utc=tracked_detection.timestamp_utc,
                    camera_id=tracked_detection.camera_id,
                    match_kind=match.match_kind,
                    matched_plate_text=best_plate.text,
                    match_confidence=best_plate.confidence,
                    match_type=match.match_type,
                    matched_attributes=match.matched_dimensions,
                    hotlist_label=entry.label,
                )

        # IN-ZONE LEAD: geofenced make/model match (no plate match required).
        if in_zone_entry_ids:
            profile_match, entry = self.match_profile_in_zone(
                tracked_detection.vehicle_attributes, hotlist_entries, in_zone_entry_ids
            )
            if profile_match.matched and entry is not None:
                return AlertRecord(
                    alert_id=f"alert_{uuid4().hex[:12]}",
                    detection_id=tracked_detection.detection_id,
                    hotlist_entry_id=entry.entry_id,
                    timestamp_utc=tracked_detection.timestamp_utc,
                    camera_id=tracked_detection.camera_id,
                    match_kind=profile_match.match_kind,
                    matched_plate_text=best_plate.text if best_plate is not None else None,
                    match_confidence=profile_match.score,
                    match_type=None,
                    matched_attributes=profile_match.matched_dimensions,
                    hotlist_label=entry.label,
                )

        return None
