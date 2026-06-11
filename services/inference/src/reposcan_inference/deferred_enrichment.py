"""Post-scan deferred enrichment.

The post-scan half of the dual-camera workflow: during the scan the real-time
pipeline records LPR detections; after the scan window closes, this service
re-runs the deferred recognition heads (make/model + re-rank + year + color)
against the stored detection crops and writes the attributes back to the
detection records — without ever blocking the real-time latency budget.

It bridges two injected collaborators:
  * a recognizer exposing ``recognize_deferred(frame, vehicle_detections)``
    (``InferenceService`` satisfies this), and
  * a storage repository exposing ``get_detection`` / ``upsert_detection``.

Both are injected (not imported concretely) so the orchestration is unit-
testable with an in-memory repository and a stub recognizer, no ONNX required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence

from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.frame import CameraProfile, FrameEnvelope, SourceType
from reposcan_contracts.inference import AttributePredictions, VehicleDetection


class DeferredRecognizer(Protocol):
    def recognize_deferred(
        self,
        frame: object,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        ...


class DetectionRepository(Protocol):
    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        ...

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        ...


@dataclass
class DeferredEnrichmentResult:
    """Outcome of enriching a single detection.

    ``enriched`` is False when no deferred pipeline is configured or the
    pipeline produced nothing to write; ``record`` is then the unchanged
    detection so callers can treat the result uniformly.
    """

    detection_id: str
    enriched: bool
    record: DetectionRecord


def _frame_from_record(record: DetectionRecord) -> FrameEnvelope:
    """Reconstruct a minimal frame pointing at the stored detection image."""
    return FrameEnvelope(
        frame_id=f"enrich_{record.detection_id}",
        camera_id=record.camera_id,
        timestamp_utc=record.timestamp_utc,
        frame_path=record.image_path,
        frame_number=record.frame_number,
        source_type=SourceType.file,
        camera_profile=CameraProfile(camera_id=record.camera_id, source_type=SourceType.file),
    )


def _detection_from_record(record: DetectionRecord) -> VehicleDetection:
    return VehicleDetection(bbox=record.vehicle_bbox, confidence=1.0, class_label="car")


def _apply_attributes(record: DetectionRecord, preds: AttributePredictions) -> DetectionRecord:
    """Write predicted attributes onto a copy of the record.

    Only fields the deferred pipeline actually produced (non-None) are
    written, so an absent head (e.g. no color classifier) never clears an
    attribute that some other stage already populated.
    """
    update: dict[str, object] = {}
    if preds.make is not None:
        update["vehicle_make"] = preds.make
        update["vehicle_make_confidence"] = preds.make_confidence
    if preds.model_label is not None:
        update["vehicle_model"] = preds.model_label
        update["vehicle_model_confidence"] = preds.model_confidence
    if preds.color is not None:
        update["vehicle_color"] = preds.color
        update["vehicle_color_confidence"] = preds.color_confidence
    if preds.year is not None:
        update["optional_vehicle_year"] = preds.year
        update["optional_year_confidence"] = preds.year_confidence
    if not update:
        return record
    return record.model_copy(update=update)


class DeferredEnrichmentService:
    """Enrich stored detections with deferred recognition attributes."""

    def __init__(self, repository: DetectionRepository, recognizer: DeferredRecognizer) -> None:
        self._repo = repository
        self._recognizer = recognizer

    def enrich_detection(self, detection_id: str) -> DeferredEnrichmentResult | None:
        """Enrich one detection by id. Returns None if the id is unknown."""
        record = self._repo.get_detection(detection_id)
        if record is None:
            return None

        predictions = self._recognizer.recognize_deferred(
            _frame_from_record(record),
            [_detection_from_record(record)],
        )
        if not predictions:
            # No deferred pipeline configured, or it produced nothing.
            return DeferredEnrichmentResult(detection_id=detection_id, enriched=False, record=record)

        enriched = _apply_attributes(record, predictions[0])
        if enriched is record:
            return DeferredEnrichmentResult(detection_id=detection_id, enriched=False, record=record)

        saved = self._repo.upsert_detection(enriched)
        return DeferredEnrichmentResult(detection_id=detection_id, enriched=True, record=saved)

    def enrich_detections(self, detection_ids: Iterable[str]) -> list[DeferredEnrichmentResult]:
        """Enrich a batch of detections (e.g. all sightings from a scan window).

        Unknown ids are skipped. Order follows the input.
        """
        results: list[DeferredEnrichmentResult] = []
        for detection_id in detection_ids:
            result = self.enrich_detection(detection_id)
            if result is not None:
                results.append(result)
        return results
