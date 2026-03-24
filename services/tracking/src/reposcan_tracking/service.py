"""Tracking service with multi-frame association, OCR fusion, and duplicate suppression."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import hypot
from typing import Iterable
from uuid import uuid4

from reposcan_contracts.config.loader import load_pipeline_config
from reposcan_contracts.config.pipeline import OcrAggregation, PipelineConfig, TrackingAlgorithm
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


def _bbox_iou(a: BoundingBox, b: BoundingBox) -> float:
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.x + a.w, b.x + b.w)
    bottom = min(a.y + a.h, b.y + b.h)
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = (a.w * a.h) + (b.w * b.h) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _shift_bbox(bbox: BoundingBox, *, dx: float, dy: float) -> BoundingBox:
    return BoundingBox(
        x=max(0, int(round(bbox.x + dx))),
        y=max(0, int(round(bbox.y + dy))),
        w=bbox.w,
        h=bbox.h,
    )


def _utc_to_epoch_seconds(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def _plate_text_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    matches = sum(1 for left, right in zip(a, b) if left == right)
    return matches / max_len


def _attribute_similarity(
    left: AttributePredictions | None,
    right: AttributePredictions | None,
) -> float:
    if left is None or right is None:
        return 0.0

    score = 0.0
    weight = 0.0
    if left.color and right.color:
        weight += 1.0
        if left.color == right.color:
            score += 1.0
    if left.make and right.make:
        weight += 1.0
        if left.make == right.make:
            score += 1.0
    if left.model_label and right.model_label:
        weight += 1.0
        if left.model_label == right.model_label:
            score += 1.0
    if left.year and right.year:
        weight += 1.0
        if left.year == right.year:
            score += 1.0
    if weight == 0.0:
        return 0.0
    return score / weight


@dataclass
class _ActiveTrack:
    tracker_id: str
    camera_id: str
    current_vehicle_bbox: BoundingBox
    current_plate_bbox: BoundingBox | None
    best_vehicle_bbox: BoundingBox
    best_plate_bbox: BoundingBox | None
    timestamp_utc: str
    frame_number: int
    best_frame_path: str
    best_frame_score: float
    hits: int = 0
    missed: int = 0
    first_seen_utc: str = ""
    last_seen_utc: str = ""
    velocity_dx: float = 0.0
    velocity_dy: float = 0.0
    ocr_candidates: list[PlateCandidate] = field(default_factory=list)
    attribute_predictions: list[AttributePredictions] = field(default_factory=list)


@dataclass
class _RecentDetection:
    camera_id: str
    timestamp_seconds: float
    vehicle_bbox: BoundingBox
    plate_text: str
    vehicle_attributes: AttributePredictions | None


class TrackingService:
    def __init__(self, pipeline_config: PipelineConfig) -> None:
        self.pipeline_config = pipeline_config
        self._active_tracks: dict[str, _ActiveTrack] = {}
        self._recent_detections: list[_RecentDetection] = []
        self._suppressed_duplicates = 0

    @classmethod
    def from_config_path(cls, config_path: str = "configs/pipelines/default-edge.yaml") -> "TrackingService":
        return cls(load_pipeline_config(config_path))

    @property
    def suppressed_duplicates(self) -> int:
        return self._suppressed_duplicates

    def snapshot_metrics(self) -> dict[str, int]:
        return {
            "active_tracks": len(self._active_tracks),
            "suppressed_duplicates": self._suppressed_duplicates,
            "recent_detection_memory": len(self._recent_detections),
        }

    def ingest(self, frame: FrameEnvelope, candidate: InferenceCandidate) -> list[TrackedDetection]:
        finalized: list[TrackedDetection] = []
        available_track_ids = {
            tracker_id
            for tracker_id, track in self._active_tracks.items()
            if track.camera_id == frame.camera_id
        }

        for vehicle_index, vehicle_detection in enumerate(candidate.vehicle_detections):
            plate_detection = self._plate_detection_for_vehicle(vehicle_index, candidate)
            attributes = self._attributes_for_vehicle(vehicle_index, candidate)
            ocr_candidates = self._ocr_candidates_for_vehicle(candidate, plate_detection)

            track = self._match_track(
                vehicle_detection,
                available_track_ids,
                plate_detection=plate_detection,
                attributes=attributes,
                ocr_candidates=ocr_candidates,
            )
            if track is None:
                track = self._create_track(frame, vehicle_detection, plate_detection)
                self._active_tracks[track.tracker_id] = track
            else:
                available_track_ids.discard(track.tracker_id)

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

    def _predicted_bbox(self, track: _ActiveTrack) -> BoundingBox:
        return _shift_bbox(
            track.current_vehicle_bbox,
            dx=track.velocity_dx,
            dy=track.velocity_dy,
        )

    def _track_plate_hint(self, track: _ActiveTrack) -> str | None:
        if not track.ocr_candidates:
            return None
        ordered = sorted(track.ocr_candidates, key=lambda item: (item.confidence, item.text), reverse=True)
        return ordered[0].text if ordered else None

    def _candidate_plate_hint(self, ocr_candidates: Iterable[PlateCandidate]) -> str | None:
        ordered = sorted(ocr_candidates, key=lambda item: (item.confidence, item.text), reverse=True)
        return ordered[0].text if ordered else None

    def _latest_attributes(self, track: _ActiveTrack) -> AttributePredictions | None:
        return track.attribute_predictions[-1] if track.attribute_predictions else None

    def _match_score(
        self,
        track: _ActiveTrack,
        vehicle_detection: VehicleDetection,
        *,
        attributes: AttributePredictions | None,
        ocr_candidates: Iterable[PlateCandidate],
    ) -> float | None:
        tracking = self.pipeline_config.tracking
        algorithm = tracking.algorithm
        direct_iou = _bbox_iou(track.current_vehicle_bbox, vehicle_detection.bbox)
        predicted_bbox = self._predicted_bbox(track)
        predicted_iou = _bbox_iou(predicted_bbox, vehicle_detection.bbox)
        direct_distance = _match_distance(track.current_vehicle_bbox, vehicle_detection.bbox)
        predicted_distance = _match_distance(predicted_bbox, vehicle_detection.bbox)
        distance_threshold = _match_threshold(track.current_vehicle_bbox, vehicle_detection.bbox)
        motion_threshold = distance_threshold + tracking.camera_motion_tolerance_px
        plate_similarity = _plate_text_similarity(self._track_plate_hint(track), self._candidate_plate_hint(ocr_candidates))
        attribute_score = _attribute_similarity(self._latest_attributes(track), attributes)

        if algorithm == TrackingAlgorithm.sort:
            if direct_iou < tracking.min_match_iou and direct_distance > distance_threshold:
                return None
            return (direct_iou * 4.0) - (direct_distance / max(distance_threshold, 1.0))

        if algorithm == TrackingAlgorithm.byte_tracker:
            best_iou = max(direct_iou, predicted_iou)
            best_distance = min(direct_distance, predicted_distance)
            if best_iou < tracking.min_match_iou and best_distance > motion_threshold:
                return None
            return (
                (best_iou * 5.0)
                + (vehicle_detection.confidence * 0.5)
                + (plate_similarity * 0.3)
                - (best_distance / max(motion_threshold, 1.0))
            )

        best_iou = max(direct_iou, predicted_iou)
        best_distance = min(direct_distance, predicted_distance)
        deep_motion_threshold = distance_threshold + (tracking.camera_motion_tolerance_px * 0.6)
        if (
            best_iou < tracking.min_match_iou
            and best_distance > deep_motion_threshold
            and plate_similarity < 0.8
            and attribute_score < 0.75
        ):
            return None
        return (
            (best_iou * 4.0)
            + (vehicle_detection.confidence * 0.3)
            + (plate_similarity * 1.2)
            + (attribute_score * 1.0)
            - (best_distance / max(deep_motion_threshold, 1.0))
        )

    def _match_track(
        self,
        vehicle_detection: VehicleDetection,
        available_track_ids: set[str],
        *,
        plate_detection: PlateDetection | None,
        attributes: AttributePredictions | None,
        ocr_candidates: Iterable[PlateCandidate],
    ) -> _ActiveTrack | None:
        del plate_detection
        best_track: _ActiveTrack | None = None
        best_score: float | None = None

        for tracker_id in available_track_ids:
            track = self._active_tracks[tracker_id]
            score = self._match_score(
                track,
                vehicle_detection,
                attributes=attributes,
                ocr_candidates=ocr_candidates,
            )
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_track = track
                best_score = score

        return best_track

    def _create_track(
        self,
        frame: FrameEnvelope,
        vehicle_detection: VehicleDetection,
        plate_detection: PlateDetection | None,
    ) -> _ActiveTrack:
        return _ActiveTrack(
            tracker_id=f"trk_{uuid4().hex[:12]}",
            camera_id=frame.camera_id,
            current_vehicle_bbox=vehicle_detection.bbox,
            current_plate_bbox=plate_detection.bbox if plate_detection is not None else None,
            best_vehicle_bbox=vehicle_detection.bbox,
            best_plate_bbox=plate_detection.bbox if plate_detection is not None else None,
            timestamp_utc=frame.timestamp_utc,
            frame_number=frame.frame_number,
            best_frame_path=frame.frame_path,
            best_frame_score=plate_detection.confidence if plate_detection is not None else vehicle_detection.confidence,
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
        if len(candidate.plate_detections) == len(candidate.ocr_candidates):
            try:
                plate_index = candidate.plate_detections.index(plate_detection)
            except ValueError:
                plate_index = -1
            if 0 <= plate_index < len(candidate.ocr_candidates):
                return [candidate.ocr_candidates[plate_index]]
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
        previous_bbox = track.current_vehicle_bbox
        previous_center = _bbox_center(previous_bbox)
        new_center = _bbox_center(vehicle_detection.bbox)
        track.velocity_dx = new_center[0] - previous_center[0]
        track.velocity_dy = new_center[1] - previous_center[1]
        track.current_vehicle_bbox = vehicle_detection.bbox
        track.current_plate_bbox = plate_detection.bbox if plate_detection is not None else None

        track.hits += 1
        track.missed = 0
        track.last_seen_utc = frame.timestamp_utc
        track.timestamp_utc = frame.timestamp_utc

        evidence_score = plate_detection.confidence if plate_detection is not None else vehicle_detection.confidence
        if evidence_score >= track.best_frame_score:
            track.best_frame_score = evidence_score
            track.best_vehicle_bbox = vehicle_detection.bbox
            track.best_plate_bbox = plate_detection.bbox if plate_detection is not None else None
            track.frame_number = frame.frame_number
            track.best_frame_path = frame.frame_path

        if attributes is not None:
            track.attribute_predictions.append(attributes)

        for ocr_candidate in ocr_candidates:
            track.ocr_candidates.append(ocr_candidate)

    def _prune_recent_detections(self, reference_seconds: float) -> None:
        window = self.pipeline_config.tracking.duplicate_suppression_window_seconds
        if window <= 0.0:
            self._recent_detections = []
            return
        self._recent_detections = [
            item
            for item in self._recent_detections
            if (reference_seconds - item.timestamp_seconds) <= window
        ]

    def _is_duplicate_detection(self, tracked_detection: TrackedDetection) -> bool:
        candidate = tracked_detection.best_plate_candidate
        tracking = self.pipeline_config.tracking
        if candidate is None:
            return False
        if candidate.confidence < tracking.duplicate_suppression_min_plate_confidence:
            return False

        timestamp_seconds = _utc_to_epoch_seconds(tracked_detection.timestamp_utc)
        self._prune_recent_detections(timestamp_seconds)
        for recent in self._recent_detections:
            if recent.camera_id != tracked_detection.camera_id:
                continue
            if recent.plate_text != candidate.text:
                continue

            iou = _bbox_iou(recent.vehicle_bbox, tracked_detection.vehicle_bbox)
            center_distance = _match_distance(recent.vehicle_bbox, tracked_detection.vehicle_bbox)
            attribute_score = _attribute_similarity(recent.vehicle_attributes, tracked_detection.vehicle_attributes)
            if (
                iou >= tracking.duplicate_suppression_min_iou
                or center_distance <= tracking.camera_motion_tolerance_px
                or attribute_score >= 0.75
            ):
                self._suppressed_duplicates += 1
                return True

        self._recent_detections.append(
            _RecentDetection(
                camera_id=tracked_detection.camera_id,
                timestamp_seconds=timestamp_seconds,
                vehicle_bbox=tracked_detection.vehicle_bbox,
                plate_text=candidate.text,
                vehicle_attributes=tracked_detection.vehicle_attributes,
            )
        )
        return False

    def _finalize_track(self, tracker_id: str) -> TrackedDetection | None:
        track = self._active_tracks.pop(tracker_id)
        if track.hits < self.pipeline_config.tracking.min_hits_to_confirm:
            return None

        best_candidate, alternates = self._aggregate_ocr_candidates(track.ocr_candidates)
        best_attribute_prediction = self._select_best_attributes(track.attribute_predictions)
        tracked_detection = TrackedDetection(
            detection_id=f"det_{uuid4().hex[:12]}",
            tracker_id=track.tracker_id,
            camera_id=track.camera_id,
            timestamp_utc=track.timestamp_utc,
            best_plate_candidate=best_candidate,
            alternate_plate_candidates=alternates,
            vehicle_bbox=track.best_vehicle_bbox,
            plate_bbox=track.best_plate_bbox,
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
        if self._is_duplicate_detection(tracked_detection):
            return None
        return tracked_detection

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
