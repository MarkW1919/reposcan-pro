"""Tracking service skeleton for multi-frame association and OCR fusion."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Iterable
from uuid import uuid4

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import OcrAggregation, PipelineConfig
from reposcan_contracts.detection import BoundingBox, PlateCandidate
from reposcan_contracts.frame import FrameEnvelope
from reposcan_contracts.inference import AttributePredictions, InferenceCandidate, PlateDetection, VehicleDetection
from reposcan_contracts.tracking import ConfidenceSummary, EvidenceRefs, TrackedDetection


def _bbox_center(bbox: BoundingBox) -> tuple[float, float]:
    return (bbox.x + (bbox.w / 2.0), bbox.y + (bbox.h / 2.0))


def _match_distance(a: BoundingBox, b: BoundingBox) -> float:
    ax, ay = _bbox_center(a)
    bx, by = _bbox_center(b)
    return hypot(ax - bx, ay - by)


def _match_threshold(a: BoundingBox, b: BoundingBox) -> float:
    return max(40.0, 0.6 * max(hypot(a.w, a.h), hypot(b.w, b.h)))


@dataclass
class _ActiveTrack:
    tracker_id: str
    camera_id: str
    vehicle_bbox: BoundingBox
    plate_bbox: BoundingBox | None
    timestamp_utc: str
    frame_number: int
    best_frame_path: str
    best_frame_score: float
    hits: int = 0
    missed: int = 0
    first_seen_utc: str = ""
    last_seen_utc: str = ""
    ocr_candidates: list[PlateCandidate] = field(default_factory=list)
    attribute_predictions: list[AttributePredictions] = field(default_factory=list)


class TrackingService:
    def __init__(self, pipeline_config: PipelineConfig) -> None:
        self.pipeline_config = pipeline_config
        self._active_tracks: dict[str, _ActiveTrack] = {}

    @classmethod
    def from_config_path(cls, config_path: str = "configs/pipelines/default-edge.yaml") -> "TrackingService":
        return cls(load_pipeline_config(config_path))

    def ingest(self, frame: FrameEnvelope, candidate: InferenceCandidate) -> list[TrackedDetection]:
        finalized: list[TrackedDetection] = []
        available_track_ids = {
            tracker_id
            for tracker_id, track in self._active_tracks.items()
            if track.camera_id == frame.camera_id
        }

        for vehicle_index, vehicle_detection in enumerate(candidate.vehicle_detections):
            track = self._match_track(vehicle_detection, available_track_ids)
            if track is None:
                track = self._create_track(frame, vehicle_detection)
                self._active_tracks[track.tracker_id] = track
            else:
                available_track_ids.discard(track.tracker_id)

            plate_detection = self._plate_detection_for_vehicle(vehicle_index, candidate)
            attributes = self._attributes_for_vehicle(vehicle_index, candidate)
            ocr_candidates = self._ocr_candidates_for_vehicle(candidate, plate_detection)
            self._update_track(track, frame, vehicle_detection, plate_detection, attributes, ocr_candidates)

        for tracker_id in list(available_track_ids):
            track = self._active_tracks[tracker_id]
            track.missed += 1
            if track.missed > self.pipeline_config.tracking.max_lost_frames:
                finalized_track = self._finalize_track(tracker_id)
                if finalized_track is not None:
                    finalized.append(finalized_track)

        return finalized

    def flush(self, *, camera_id: str | None = None) -> list[TrackedDetection]:
        finalized: list[TrackedDetection] = []
        for tracker_id in list(self._active_tracks.keys()):
            track = self._active_tracks[tracker_id]
            if camera_id is not None and track.camera_id != camera_id:
                continue
            finalized_track = self._finalize_track(tracker_id)
            if finalized_track is not None:
                finalized.append(finalized_track)
        return finalized

    def _match_track(
        self,
        vehicle_detection: VehicleDetection,
        available_track_ids: set[str],
    ) -> _ActiveTrack | None:
        best_track: _ActiveTrack | None = None
        best_distance: float | None = None

        for tracker_id in available_track_ids:
            track = self._active_tracks[tracker_id]
            distance = _match_distance(track.vehicle_bbox, vehicle_detection.bbox)
            if distance > _match_threshold(track.vehicle_bbox, vehicle_detection.bbox):
                continue
            if best_distance is None or distance < best_distance:
                best_track = track
                best_distance = distance

        return best_track

    def _create_track(self, frame: FrameEnvelope, vehicle_detection: VehicleDetection) -> _ActiveTrack:
        return _ActiveTrack(
            tracker_id=f"trk_{uuid4().hex[:12]}",
            camera_id=frame.camera_id,
            vehicle_bbox=vehicle_detection.bbox,
            plate_bbox=None,
            timestamp_utc=frame.timestamp_utc,
            frame_number=frame.frame_number,
            best_frame_path=frame.frame_path,
            best_frame_score=vehicle_detection.confidence,
            first_seen_utc=frame.timestamp_utc,
            last_seen_utc=frame.timestamp_utc,
        )

    def _plate_detection_for_vehicle(
        self,
        vehicle_index: int,
        candidate: InferenceCandidate,
    ) -> PlateDetection | None:
        for plate_detection in candidate.plate_detections:
            if plate_detection.vehicle_index == vehicle_index:
                return plate_detection
        if len(candidate.vehicle_detections) == 1 and len(candidate.plate_detections) == 1:
            return candidate.plate_detections[0]
        return None

    def _ocr_candidates_for_vehicle(
        self,
        candidate: InferenceCandidate,
        plate_detection: PlateDetection | None,
    ) -> list[PlateCandidate]:
        if plate_detection is None:
            return []
        return list(candidate.ocr_candidates)

    def _attributes_for_vehicle(
        self,
        vehicle_index: int,
        candidate: InferenceCandidate,
    ) -> AttributePredictions | None:
        if vehicle_index < len(candidate.attribute_predictions):
            return candidate.attribute_predictions[vehicle_index]
        return None

    def _update_track(
        self,
        track: _ActiveTrack,
        frame: FrameEnvelope,
        vehicle_detection: VehicleDetection,
        plate_detection: PlateDetection | None,
        attributes: AttributePredictions | None,
        ocr_candidates: Iterable[PlateCandidate],
    ) -> None:
        track.hits += 1
        track.missed = 0
        track.last_seen_utc = frame.timestamp_utc
        track.timestamp_utc = frame.timestamp_utc

        evidence_score = plate_detection.confidence if plate_detection is not None else vehicle_detection.confidence
        if evidence_score >= track.best_frame_score:
            track.best_frame_score = evidence_score
            track.vehicle_bbox = vehicle_detection.bbox
            track.plate_bbox = plate_detection.bbox if plate_detection is not None else None
            track.frame_number = frame.frame_number
            track.best_frame_path = frame.frame_path

        if attributes is not None:
            track.attribute_predictions.append(attributes)

        for ocr_candidate in ocr_candidates:
            track.ocr_candidates.append(ocr_candidate)

    def _finalize_track(self, tracker_id: str) -> TrackedDetection | None:
        track = self._active_tracks.pop(tracker_id)
        if track.hits < self.pipeline_config.tracking.min_hits_to_confirm:
            return None

        best_candidate, alternates = self._aggregate_ocr_candidates(track.ocr_candidates)
        best_attribute_prediction = self._select_best_attributes(track.attribute_predictions)
        return TrackedDetection(
            detection_id=f"det_{uuid4().hex[:12]}",
            tracker_id=track.tracker_id,
            camera_id=track.camera_id,
            timestamp_utc=track.timestamp_utc,
            best_plate_candidate=best_candidate,
            alternate_plate_candidates=alternates,
            vehicle_bbox=track.vehicle_bbox,
            plate_bbox=track.plate_bbox,
            vehicle_attributes=best_attribute_prediction,
            evidence_refs=EvidenceRefs(best_frame_path=track.best_frame_path),
            confidence_summary=ConfidenceSummary(
                best_plate_confidence=best_candidate.confidence if best_candidate is not None else None,
                ocr_candidate_count=len(track.ocr_candidates),
                frames_tracked=track.hits,
                first_seen_utc=track.first_seen_utc,
                last_seen_utc=track.last_seen_utc,
            ),
            frame_number=track.frame_number,
        )

    def _aggregate_ocr_candidates(
        self,
        ocr_candidates: list[PlateCandidate],
    ) -> tuple[PlateCandidate | None, list[PlateCandidate]]:
        if not ocr_candidates:
            return None, []

        summaries: dict[str, dict[str, float]] = {}
        for candidate in ocr_candidates:
            summary = summaries.setdefault(candidate.text, {"count": 0.0, "best_conf": 0.0, "sum_conf": 0.0})
            summary["count"] += 1.0
            summary["best_conf"] = max(summary["best_conf"], candidate.confidence)
            summary["sum_conf"] += candidate.confidence

        ranked: list[tuple[float, PlateCandidate]] = []
        for text, summary in summaries.items():
            if self.pipeline_config.tracking.ocr_aggregation == OcrAggregation.best_confidence:
                score = summary["best_conf"]
            elif self.pipeline_config.tracking.ocr_aggregation == OcrAggregation.ensemble:
                score = summary["sum_conf"]
            else:
                score = (summary["count"] * 10.0) + summary["best_conf"]
            ranked.append((score, PlateCandidate(text=text, confidence=summary["best_conf"])))

        ranked.sort(key=lambda item: (item[0], item[1].confidence, item[1].text), reverse=True)
        ordered_candidates = [candidate for _, candidate in ranked]
        promoted = ordered_candidates[0]
        if (
            len(ocr_candidates) < self.pipeline_config.fusion.min_ocr_candidates_for_promotion
            or promoted.confidence < self.pipeline_config.fusion.promote_best_read_threshold
        ):
            return None, ordered_candidates

        return promoted, ordered_candidates[1:]

    def _select_best_attributes(
        self,
        attribute_predictions: list[AttributePredictions],
    ) -> AttributePredictions | None:
        if not attribute_predictions:
            return None

        def score(prediction: AttributePredictions) -> float:
            return sum(
                value or 0.0
                for value in (
                    prediction.color_confidence,
                    prediction.make_confidence,
                    prediction.model_confidence,
                    prediction.year_confidence,
                )
            )

        return max(attribute_predictions, key=score)
