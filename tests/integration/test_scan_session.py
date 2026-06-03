"""Tests for the scan-session state machine and enrichment trigger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest

from reposcan_contracts.detection import BoundingBox, DetectionRecord
from reposcan_contracts.inference import AttributePredictions, VehicleDetection
from reposcan_contracts.operator import ScanSessionState
from reposcan_inference.deferred_enrichment import DeferredEnrichmentService
from reposcan_inference.scan_session import (
    ScanSessionEnrichmentCoordinator,
    ScanSessionTracker,
)
from reposcan_storage.memory import InMemoryStorageRepository


RADIUS = 300.0


def _tracker() -> ScanSessionTracker:
    return ScanSessionTracker(radius_feet=RADIUS)


# --- state machine ---------------------------------------------------------


def test_rejects_nonpositive_radius():
    with pytest.raises(ValueError):
        ScanSessionTracker(radius_feet=0)


def test_idle_when_not_navigating():
    t = _tracker()
    result = t.update(navigation_active=False, distance_feet=None)
    assert result.state == ScanSessionState.idle
    assert result.changed is False  # already idle


def test_approaching_then_active_on_entry():
    t = _tracker()
    approaching = t.update(navigation_active=True, distance_feet=1000.0)
    assert approaching.state == ScanSessionState.approaching_radius
    assert approaching.changed is True

    active = t.update(navigation_active=True, distance_feet=250.0)
    assert active.state == ScanSessionState.active_lpr_scan
    assert active.changed is True


def test_navigating_without_distance_is_idle():
    t = _tracker()
    result = t.update(navigation_active=True, distance_feet=None)
    assert result.state == ScanSessionState.idle


def test_window_closes_on_radius_exit_and_surfaces_ids_once():
    t = _tracker()
    t.update(navigation_active=True, distance_feet=250.0)  # active
    t.record_detection("d1")
    t.record_detection("d2")

    exit_update = t.update(navigation_active=True, distance_feet=400.0)  # left radius
    assert exit_update.state == ScanSessionState.post_scan_vehicle_enrichment
    assert exit_update.closed_window_detection_ids == ["d1", "d2"]

    # Ids are surfaced only once — the next sample does not replay them.
    next_update = t.update(navigation_active=True, distance_feet=500.0)
    assert next_update.closed_window_detection_ids == []
    assert next_update.state == ScanSessionState.completed


def test_window_closes_when_route_ends_mid_scan():
    t = _tracker()
    t.update(navigation_active=True, distance_feet=100.0)  # active
    t.record_detection("d1")
    ended = t.update(navigation_active=False, distance_feet=None)
    assert ended.state == ScanSessionState.post_scan_vehicle_enrichment
    assert ended.closed_window_detection_ids == ["d1"]


def test_detections_only_buffered_while_active():
    t = _tracker()
    # Not scanning yet — these should be ignored.
    t.update(navigation_active=True, distance_feet=1000.0)  # approaching
    t.record_detection("ignored")
    t.update(navigation_active=True, distance_feet=200.0)  # active
    t.record_detection("kept")
    closed = t.update(navigation_active=True, distance_feet=900.0)
    assert closed.closed_window_detection_ids == ["kept"]


def test_recenter_rescans_fresh_window():
    t = _tracker()
    t.update(navigation_active=True, distance_feet=100.0)  # active
    t.record_detection("first_pass")
    t.update(navigation_active=True, distance_feet=900.0)  # close -> post_scan
    t.update(navigation_active=True, distance_feet=900.0)  # -> completed
    # Circle back into the radius: a fresh window, no stale ids.
    reentry = t.update(navigation_active=True, distance_feet=100.0)
    assert reentry.state == ScanSessionState.active_lpr_scan
    t.record_detection("second_pass")
    closed = t.update(navigation_active=True, distance_feet=900.0)
    assert closed.closed_window_detection_ids == ["second_pass"]


def test_radius_boundary_is_inclusive():
    t = _tracker()
    t.update(navigation_active=True, distance_feet=1000.0)
    at_edge = t.update(navigation_active=True, distance_feet=RADIUS)  # exactly on radius
    assert at_edge.state == ScanSessionState.active_lpr_scan


# --- coordinator + enrichment ---------------------------------------------


@dataclass
class StubRecognizer:
    make: str

    def recognize_deferred(
        self,
        frame: object,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        return [AttributePredictions(make=self.make, make_confidence=0.9) for _ in vehicle_detections]


def _seed(repo: InMemoryStorageRepository, detection_id: str) -> None:
    repo.upsert_detection(
        DetectionRecord(
            detection_id=detection_id,
            timestamp_utc="2026-06-02T12:00:00Z",
            camera_id="cam_01",
            vehicle_bbox=BoundingBox(x=0, y=0, w=100, h=80),
            image_path="data/curated/sample.jpg",
            frame_number=0,
        )
    )


def test_coordinator_enriches_closed_window():
    repo = InMemoryStorageRepository()
    _seed(repo, "d1")
    _seed(repo, "d2")
    enrichment = DeferredEnrichmentService(repo, StubRecognizer(make="ford_f_series"))
    coordinator = ScanSessionEnrichmentCoordinator(ScanSessionTracker(radius_feet=RADIUS), enrichment)

    coordinator.update(navigation_active=True, distance_feet=200.0)  # active
    coordinator.record_detection("d1")
    coordinator.record_detection("d2")

    outcome = coordinator.update(navigation_active=True, distance_feet=800.0)  # window closes

    assert outcome.update.state == ScanSessionState.post_scan_vehicle_enrichment
    assert {r.detection_id for r in outcome.enrichment_results} == {"d1", "d2"}
    assert all(r.enriched for r in outcome.enrichment_results)
    assert repo.get_detection("d1").vehicle_make == "ford_f_series"
    assert repo.get_detection("d2").vehicle_make == "ford_f_series"


def test_coordinator_no_enrichment_until_window_closes():
    repo = InMemoryStorageRepository()
    _seed(repo, "d1")
    enrichment = DeferredEnrichmentService(repo, StubRecognizer(make="toyota_camry"))
    coordinator = ScanSessionEnrichmentCoordinator(ScanSessionTracker(radius_feet=RADIUS), enrichment)

    approaching = coordinator.update(navigation_active=True, distance_feet=900.0)
    assert approaching.enrichment_results == []
    active = coordinator.update(navigation_active=True, distance_feet=100.0)
    assert active.enrichment_results == []
    coordinator.record_detection("d1")
    # Still inside radius — no enrichment yet.
    still_active = coordinator.update(navigation_active=True, distance_feet=120.0)
    assert still_active.enrichment_results == []
    assert repo.get_detection("d1").vehicle_make is None
