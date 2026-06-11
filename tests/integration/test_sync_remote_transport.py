from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.detection import DetectionRecord, SyncStatus
from reposcan_storage.memory import InMemoryStorageRepository
from reposcan_storage.service import StorageService
from reposcan_sync import HttpSyncTransport, JsonSyncQueue, SyncService, create_development_sync_service
from reposcan_alerting import create_alert_delivery_service_from_deployment


REPO_ROOT = Path(__file__).resolve().parents[2]


class _FixtureState:
    def __init__(self) -> None:
        self.sync_fail_once_ids: set[str] = set()
        self.sync_failed_once_ids: set[str] = set()
        self.sync_unique_ids: set[str] = set()
        self.sync_posts = 0
        self.alert_unique_ids: set[str] = set()
        self.alert_posts = 0


class _FixtureHandler(BaseHTTPRequestHandler):
    server_version = "RepoScanFixture/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args
        return

    def _json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(content_length).decode("utf-8")
        return json.loads(payload) if payload else {}

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        state: _FixtureState = self.server.state  # type: ignore[attr-defined]
        payload = self._json_body()

        if self.path == "/sync/detections":
            state.sync_posts += 1
            detection_id = payload["detection_id"]
            if detection_id in state.sync_fail_once_ids and detection_id not in state.sync_failed_once_ids:
                state.sync_failed_once_ids.add(detection_id)
                self._send_json(503, {"status": "temporary_unavailable"})
                return
            if detection_id in state.sync_unique_ids:
                self._send_json(409, {"status": "already_exists", "idempotent": True})
                return
            state.sync_unique_ids.add(detection_id)
            self._send_json(201, {"status": "accepted"})
            return

        if self.path == "/alerts/webhook":
            state.alert_posts += 1
            alert_id = payload["alert_id"]
            if alert_id in state.alert_unique_ids:
                self._send_json(409, {"status": "already_exists", "idempotent": True})
                return
            state.alert_unique_ids.add(alert_id)
            self._send_json(202, {"status": "accepted"})
            return

        self._send_json(404, {"status": "not_found"})


class _FixtureServer:
    def __init__(self) -> None:
        self.state = _FixtureState()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        self._server.state = self.state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_FixtureServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)

    @property
    def sync_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/sync/detections"

    @property
    def alert_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/alerts/webhook"


def _detection() -> DetectionRecord:
    return DetectionRecord.model_validate(
        {
            "detection_id": "det_sync_http_001",
            "timestamp_utc": "2026-03-24T23:55:00Z",
            "camera_id": "cam_sync_http_01",
            "vehicle_bbox": {"x": 10, "y": 20, "w": 120, "h": 80},
            "image_path": "media/frames/cam_sync_http_01/frame_000001.jpg",
            "frame_number": 1,
        }
    )


def _alert() -> AlertRecord:
    return AlertRecord.model_validate(
        {
            "alert_id": "alert_sync_http_001",
            "detection_id": "det_sync_http_001",
            "hotlist_entry_id": "hl_sync_http_001",
            "timestamp_utc": "2026-03-24T23:56:00Z",
            "camera_id": "cam_sync_http_01",
            "matched_plate_text": "8ABC123",
            "match_confidence": 0.94,
            "match_type": "exact",
            "hotlist_label": "Remote sync test",
        }
    )


def test_http_sync_transport_replays_to_real_endpoint_with_retry_and_idempotent_conflict(tmp_path):
    with _FixtureServer() as server:
        server.state.sync_fail_once_ids.add("det_sync_http_001")

        storage = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
        detection = storage.store_detection(_detection())
        service = SyncService(
            storage_service=storage,
            transport=HttpSyncTransport(endpoint_url=server.sync_url, timeout_seconds=1.0),
            queue=JsonSyncQueue(tmp_path / "queue.json"),
            retry_base_seconds=5,
            retry_max_seconds=60,
        )

        service.enqueue_detection(detection.detection_id, available_at_utc="2026-03-24T23:55:00Z")
        first = service.run_once(now_utc="2026-03-24T23:55:00Z")
        queued_item = service.queue.list_items()[0]

        assert first.failed == 1
        assert storage.get_detection(detection.detection_id).sync_status == SyncStatus.failed
        assert queued_item.attempts == 1
        assert server.state.sync_posts == 1

        second = service.run_once(now_utc=queued_item.available_at_utc)
        assert second.synced == 1
        assert storage.get_detection(detection.detection_id).sync_status == SyncStatus.synced
        assert service.queue.list_items() == []
        assert server.state.sync_posts == 2
        assert server.state.sync_unique_ids == {"det_sync_http_001"}

        service.enqueue_detection(detection.detection_id, available_at_utc="2026-03-25T00:01:00Z")
        third = service.run_once(now_utc="2026-03-25T00:01:00Z")

        assert third.synced == 1
        assert storage.get_detection(detection.detection_id).sync_status == SyncStatus.synced
        assert service.queue.list_items() == []
        assert server.state.sync_posts == 3
        assert server.state.sync_unique_ids == {"det_sync_http_001"}


def test_create_development_sync_service_selects_http_transport_when_enabled(tmp_path):
    with _FixtureServer() as server:
        deployment_data = yaml.safe_load((REPO_ROOT / "configs" / "deployments" / "local-dev.yaml").read_text(encoding="utf-8"))
        deployment_data["enabled_services"]["sync"] = True
        deployment_data["remote_sync"] = {
            "enabled": True,
            "endpoint_url": server.sync_url,
            "timeout_seconds": 1.0,
        }
        deployment_path = tmp_path / "deployment-sync-http.yaml"
        deployment_path.write_text(yaml.safe_dump(deployment_data, sort_keys=False), encoding="utf-8")

        storage = StorageService(repository=InMemoryStorageRepository(), media_root=tmp_path / "media")
        service = create_development_sync_service(
            deployment_config_path=deployment_path,
            queue_path=tmp_path / "queue.json",
            storage_service=storage,
        )

        assert type(service.transport).__name__ == "HttpSyncTransport"


def test_alert_webhook_delivery_reaches_real_endpoint_and_handles_duplicate(tmp_path):
    with _FixtureServer() as server:
        deployment_data = yaml.safe_load((REPO_ROOT / "configs" / "deployments" / "local-dev.yaml").read_text(encoding="utf-8"))
        deployment_data["alert_delivery"] = {
            "enabled": True,
            "webhook_url": server.alert_url,
            "timeout_seconds": 1.0,
        }
        deployment_path = tmp_path / "deployment-alert-webhook.yaml"
        deployment_path.write_text(yaml.safe_dump(deployment_data, sort_keys=False), encoding="utf-8")

        delivery_service = create_alert_delivery_service_from_deployment(
            deployment_config_path=deployment_path,
        )

        assert delivery_service is not None
        delivery_service.deliver(_alert())
        delivery_service.deliver(_alert())

        assert server.state.alert_posts == 2
        assert server.state.alert_unique_ids == {"alert_sync_http_001"}
