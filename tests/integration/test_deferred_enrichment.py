"""Tests for post-scan deferred enrichment of stored detections.

Uses the real in-memory storage repository plus stub recognizers, so the
orchestration (load -> recognize_deferred -> write back) is exercised without
ONNX or real artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from reposcan_contracts.detection import BoundingBox, DetectionRecord
from reposcan_contracts.inference import AttributePredictions, VehicleDetection
from reposcan_inference.deferred_enrichment import DeferredEnrichmentService
from reposcan_storage.memory import InMemoryStorageRepository


@dataclass
class StubRecognizer:
    """Returns a fixed prediction list, or [] to simulate no deferred pipeline."""

    predictions: list[AttributePredictions]

    def recognize_deferred(
        self,
        frame: object,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        return list(self.predictions)


def _record(detection_id: str) -> DetectionRecord:
    return DetectionRecord(
        detection_id=detection_id,
        timestamp_utc="2026-06-02T12:00:00Z",
        camera_id="cam_01",
        vehicle_bbox=BoundingBox(x=0, y=0, w=100, h=80),
        image_path="data/curated/sample.jpg",
        frame_number=0,
    )


def _seed(repo: InMemoryStorageRepository, detection_id: str) -> None:
    repo.upsert_detection(_record(detection_id))


def test_enrich_writes_make_model_year_color_back():
    repo = InMemoryStorageRepository()
    _seed(repo, "det_1")
    recognizer = StubRecognizer(
        predictions=[
            AttributePredictions.model_validate(
                {
                    "make": "chevrolet_silverado",
                    "make_confidence": 0.88,
                    "model": "silverado",
                    "model_confidence": 0.88,
                    "year": "bucket_2019_2022",
                    "year_confidence": 0.7,
                    "color": "white",
                    "color_confidence": 0.65,
                }
            )
        ]
    )
    service = DeferredEnrichmentService(repo, recognizer)

    result = service.enrich_detection("det_1")

    assert result is not None
    assert result.enriched is True
    stored = repo.get_detection("det_1")
    assert stored.vehicle_make == "chevrolet_silverado"
    assert stored.vehicle_make_confidence == 0.88
    assert stored.vehicle_model == "silverado"
    assert stored.optional_vehicle_year == "bucket_2019_2022"
    assert stored.vehicle_color == "white"
    assert stored.vehicle_color_confidence == 0.65


def test_enrich_unknown_id_returns_none():
    repo = InMemoryStorageRepository()
    service = DeferredEnrichmentService(repo, StubRecognizer(predictions=[]))
    assert service.enrich_detection("missing") is None


def test_enrich_no_deferred_pipeline_leaves_record_unchanged():
    repo = InMemoryStorageRepository()
    _seed(repo, "det_2")
    service = DeferredEnrichmentService(repo, StubRecognizer(predictions=[]))

    result = service.enrich_detection("det_2")

    assert result is not None
    assert result.enriched is False
    stored = repo.get_detection("det_2")
    assert stored.vehicle_make is None  # untouched


def test_enrich_absent_head_does_not_clear_existing_attribute():
    # A prediction with only make/model (no color/year) must not wipe an
    # existing color that some earlier stage populated.
    repo = InMemoryStorageRepository()
    base = _record("det_3").model_copy(update={"vehicle_color": "black", "vehicle_color_confidence": 0.9})
    repo.upsert_detection(base)
    recognizer = StubRecognizer(
        predictions=[AttributePredictions(make="ford_f_series", make_confidence=0.95)]
    )
    service = DeferredEnrichmentService(repo, recognizer)

    service.enrich_detection("det_3")

    stored = repo.get_detection("det_3")
    assert stored.vehicle_make == "ford_f_series"
    assert stored.vehicle_color == "black"  # preserved
    assert stored.vehicle_color_confidence == 0.9


def test_enrich_detections_batch_skips_unknown():
    repo = InMemoryStorageRepository()
    _seed(repo, "det_a")
    _seed(repo, "det_b")
    recognizer = StubRecognizer(
        predictions=[AttributePredictions(make="toyota_camry", make_confidence=0.8)]
    )
    service = DeferredEnrichmentService(repo, recognizer)

    results = service.enrich_detections(["det_a", "missing", "det_b"])

    assert [r.detection_id for r in results] == ["det_a", "det_b"]
    assert all(r.enriched for r in results)
    assert repo.get_detection("det_a").vehicle_make == "toyota_camry"
    assert repo.get_detection("det_b").vehicle_make == "toyota_camry"
