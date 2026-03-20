"""Transport interfaces for optional remote sync."""

from __future__ import annotations

from typing import Protocol

from reposcan_contracts.detection import DetectionRecord


class SyncTransport(Protocol):
    def send_detection(self, detection: DetectionRecord) -> None:
        ...


class MemorySyncTransport:
    def __init__(self) -> None:
        self.sent_detections: list[DetectionRecord] = []

    def send_detection(self, detection: DetectionRecord) -> None:
        self.sent_detections.append(detection)


class FlakySyncTransport:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self._attempts = 0
        self.sent_detections: list[DetectionRecord] = []

    def send_detection(self, detection: DetectionRecord) -> None:
        self._attempts += 1
        if self._attempts <= self.failures_before_success:
            raise RuntimeError("upstream unavailable")
        self.sent_detections.append(detection)
