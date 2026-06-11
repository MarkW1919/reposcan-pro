"""Scan-session state machine and deferred-enrichment trigger.

This is the GPS-driven trigger that was the last missing piece of the
dual-camera deferred workflow. As the unit drives toward a recovery target,
the operator passes through scan-session states:

    idle -> approaching_radius -> active_lpr_scan
         -> post_scan_vehicle_enrichment -> completed

While in ``active_lpr_scan`` the real-time pipeline records LPR detections;
the moment the unit leaves the scan radius (or ends the route), the scan
window closes and those buffered detections are handed to deferred
enrichment (make/model + re-rank + year + color) off the real-time path.

``ScanSessionTracker`` is a pure state machine driven by distance-to-target
samples — no GPS hardware, clock, or I/O — so transitions are exhaustively
unit-testable. ``ScanSessionEnrichmentCoordinator`` couples it to a
``DeferredEnrichmentService`` so a closed window auto-enriches.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reposcan_contracts.operator import ScanSessionState

from .deferred_enrichment import DeferredEnrichmentResult, DeferredEnrichmentService


@dataclass
class ScanSessionUpdate:
    """Result of feeding one distance sample to the tracker."""

    state: ScanSessionState
    changed: bool
    # Detection ids buffered during the scan window that just closed. Non-empty
    # only on the active_lpr_scan -> post_scan_vehicle_enrichment transition.
    closed_window_detection_ids: list[str] = field(default_factory=list)


class ScanSessionTracker:
    """Pure proximity-driven scan-session state machine.

    Feed it ``update(navigation_active, distance_feet)`` samples and
    ``record_detection(id)`` for LPR reads. It buffers detection ids while
    actively scanning and surfaces them once when the window closes.
    """

    def __init__(self, *, radius_feet: float) -> None:
        if radius_feet <= 0:
            raise ValueError("radius_feet must be positive")
        self._radius_feet = float(radius_feet)
        self._state = ScanSessionState.idle
        self._window: list[str] = []

    @property
    def state(self) -> ScanSessionState:
        return self._state

    @property
    def radius_feet(self) -> float:
        return self._radius_feet

    def record_detection(self, detection_id: str) -> None:
        """Buffer an LPR detection id; only retained while actively scanning."""
        if self._state == ScanSessionState.active_lpr_scan:
            self._window.append(detection_id)

    def _drain_window(self) -> list[str]:
        ids = self._window
        self._window = []
        return ids

    def update(self, *, navigation_active: bool, distance_feet: float | None) -> ScanSessionUpdate:
        prev = self._state
        closed: list[str] = []

        has_distance = navigation_active and distance_feet is not None
        within = has_distance and distance_feet is not None and distance_feet <= self._radius_feet

        if not navigation_active:
            # Route ended. If we were scanning, close the window; otherwise the
            # post-scan/completed states wind down, and anything else resets.
            if prev == ScanSessionState.active_lpr_scan:
                closed = self._drain_window()
                next_state = ScanSessionState.post_scan_vehicle_enrichment
            elif prev == ScanSessionState.post_scan_vehicle_enrichment:
                next_state = ScanSessionState.completed
            else:
                next_state = ScanSessionState.idle
        elif within:
            # Inside the radius: (re)arm the scan window. Re-entry from a prior
            # post_scan/completed approach starts a fresh window (drained on the
            # previous close), so circling back re-scans.
            next_state = ScanSessionState.active_lpr_scan
        else:
            # Navigating, outside the radius.
            if prev == ScanSessionState.active_lpr_scan:
                closed = self._drain_window()
                next_state = ScanSessionState.post_scan_vehicle_enrichment
            elif prev == ScanSessionState.post_scan_vehicle_enrichment:
                next_state = ScanSessionState.completed
            elif prev == ScanSessionState.completed:
                next_state = ScanSessionState.completed
            elif has_distance:
                next_state = ScanSessionState.approaching_radius
            else:
                next_state = ScanSessionState.idle

        self._state = next_state
        return ScanSessionUpdate(
            state=next_state,
            changed=next_state != prev,
            closed_window_detection_ids=closed,
        )


@dataclass
class ScanSessionEnrichmentOutcome:
    """Coordinator result: the session update plus any enrichment that ran."""

    update: ScanSessionUpdate
    enrichment_results: list[DeferredEnrichmentResult] = field(default_factory=list)


class ScanSessionEnrichmentCoordinator:
    """Drive a ScanSessionTracker and auto-enrich detections when a window closes."""

    def __init__(self, tracker: ScanSessionTracker, enrichment_service: DeferredEnrichmentService) -> None:
        self._tracker = tracker
        self._enrichment = enrichment_service

    @property
    def state(self) -> ScanSessionState:
        return self._tracker.state

    def record_detection(self, detection_id: str) -> None:
        self._tracker.record_detection(detection_id)

    def update(self, *, navigation_active: bool, distance_feet: float | None) -> ScanSessionEnrichmentOutcome:
        result = self._tracker.update(navigation_active=navigation_active, distance_feet=distance_feet)
        enrichment_results: list[DeferredEnrichmentResult] = []
        if result.closed_window_detection_ids:
            enrichment_results = self._enrichment.enrich_detections(result.closed_window_detection_ids)
        return ScanSessionEnrichmentOutcome(update=result, enrichment_results=enrichment_results)
