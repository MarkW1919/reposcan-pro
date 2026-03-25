"""Transport interfaces for optional remote sync."""

from __future__ import annotations

import json
from typing import Any
from typing import Protocol
from urllib import error, request

from reposcan_contracts.detection import DetectionRecord


class SyncTransport(Protocol):
    def send_detection(self, detection: DetectionRecord) -> None:
        ...


class RetryableSyncTransportError(RuntimeError):
    pass


class PermanentSyncTransportError(RuntimeError):
    pass


class IdempotentSyncConflict(RuntimeError):
    pass


class MemorySyncTransport:
    def __init__(self) -> None:
        self.sent_detections: list[DetectionRecord] = []

    def send_detection(self, detection: DetectionRecord) -> None:
        self.sent_detections.append(detection)


def _load_error_body(exc: error.HTTPError) -> dict[str, Any]:
    try:
        payload = exc.read().decode("utf-8")
        return json.loads(payload) if payload else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


class HttpSyncTransport:
    def __init__(
        self,
        *,
        endpoint_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def send_detection(self, detection: DetectionRecord) -> None:
        payload = json.dumps(detection.model_dump(mode="json")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": detection.detection_id,
            "X-RepoScan-Record-Type": "detection",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        outbound_request = request.Request(
            self.endpoint_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(outbound_request, timeout=self.timeout_seconds) as response:
                if response.status >= 400:
                    raise RetryableSyncTransportError(f"sync endpoint returned HTTP {response.status}")
                return
        except error.HTTPError as exc:
            body = _load_error_body(exc)
            if exc.code == 409 and (
                body.get("idempotent") is True
                or body.get("status") == "already_exists"
                or body.get("status") == "duplicate"
            ):
                raise IdempotentSyncConflict(str(body or "idempotent conflict")) from exc
            if exc.code in (408, 429) or exc.code >= 500:
                raise RetryableSyncTransportError(f"remote sync retryable HTTP {exc.code}") from exc
            raise PermanentSyncTransportError(f"remote sync rejected HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RetryableSyncTransportError(f"remote sync unavailable: {exc.reason}") from exc


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
