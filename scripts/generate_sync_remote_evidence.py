from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


_FIXED_TIMESTAMP = "2026-03-25T00:15:00Z"


def _configure_pythonpath(repo_root: Path) -> None:
    source_roots = [
        repo_root / "packages" / "contracts" / "src",
        repo_root / "services" / "storage" / "src",
        repo_root / "services" / "sync" / "src",
        repo_root / "services" / "alerting" / "src",
    ]
    for source_root in reversed(source_roots):
        sys.path.insert(0, str(source_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible Section 7 remote sync and alert-delivery evidence.",
    )
    parser.add_argument("--output-root", default="services/sync/fixtures")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


class _FixtureState:
    def __init__(self) -> None:
        self.sync_fail_once_ids: set[str] = set()
        self.sync_failed_once_ids: set[str] = set()
        self.sync_unique_ids: set[str] = set()
        self.sync_posts = 0
        self.alert_unique_ids: set[str] = set()
        self.alert_posts = 0


class _FixtureHandler(BaseHTTPRequestHandler):
    server_version = "RepoScanSyncFixture/1.0"

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


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _configure_pythonpath(repo_root)

    from reposcan_contracts.alert import AlertRecord
    from reposcan_contracts.detection import DetectionRecord
    from reposcan_storage.memory import InMemoryStorageRepository
    from reposcan_storage.service import StorageService
    from reposcan_sync import HttpSyncTransport, JsonSyncQueue, SyncService
    from reposcan_alerting import AlertDeliveryService, WebhookAlertDeliveryTransport

    args = parse_args()
    output_root = (repo_root / args.output_root).resolve() if not Path(args.output_root).is_absolute() else Path(args.output_root).resolve()
    report_path = output_root / "reports" / "remote-sync-validation.json"
    if report_path.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite existing report without --overwrite: {report_path}")

    with tempfile.TemporaryDirectory() as temp_root_str:
        temp_root = Path(temp_root_str)
        queue_path = temp_root / "queue.json"
        media_root = temp_root / "media"
        storage = StorageService(repository=InMemoryStorageRepository(), media_root=media_root)
        detection = storage.store_detection(
            DetectionRecord.model_validate(
                {
                    "detection_id": "det_sync_http_001",
                    "timestamp_utc": "2026-03-25T00:00:00Z",
                    "camera_id": "cam_sync_http_01",
                    "vehicle_bbox": {"x": 10, "y": 20, "w": 120, "h": 80},
                    "image_path": "media/frames/cam_sync_http_01/frame_000001.jpg",
                    "frame_number": 1,
                }
            )
        )
        alert = AlertRecord.model_validate(
            {
                "alert_id": "alert_sync_http_001",
                "detection_id": detection.detection_id,
                "hotlist_entry_id": "hl_sync_http_001",
                "timestamp_utc": "2026-03-25T00:01:00Z",
                "camera_id": detection.camera_id,
                "matched_plate_text": "8ABC123",
                "match_confidence": 0.94,
                "match_type": "exact",
                "hotlist_label": "Remote sync evidence",
            }
        )

        with _FixtureServer() as server:
            server.state.sync_fail_once_ids.add(detection.detection_id)

            sync_service = SyncService(
                storage_service=storage,
                transport=HttpSyncTransport(endpoint_url=server.sync_url, timeout_seconds=1.0),
                queue=JsonSyncQueue(queue_path),
                retry_base_seconds=5,
                retry_max_seconds=60,
            )
            sync_service.enqueue_detection(detection.detection_id, available_at_utc="2026-03-25T00:00:00Z")
            first = sync_service.run_once(now_utc="2026-03-25T00:00:00Z")
            queued_item = sync_service.queue.list_items()[0]
            second = sync_service.run_once(now_utc=queued_item.available_at_utc)
            sync_service.enqueue_detection(detection.detection_id, available_at_utc="2026-03-25T00:10:00Z")
            third = sync_service.run_once(now_utc="2026-03-25T00:10:00Z")

            delivery_service = AlertDeliveryService(
                WebhookAlertDeliveryTransport(
                    webhook_url=server.alert_url,
                    timeout_seconds=1.0,
                )
            )
            delivery_service.deliver(alert)
            delivery_service.deliver(alert)

            final_detection = storage.get_detection(detection.detection_id)
            report = {
                "generated_at_utc": _FIXED_TIMESTAMP,
                "sync_transport": {
                    "first_run_failed": first.failed,
                    "retry_run_synced": second.synced,
                    "idempotent_replay_synced": third.synced,
                    "remote_unique_detections": len(server.state.sync_unique_ids),
                    "remote_sync_posts": server.state.sync_posts,
                    "final_sync_status": final_detection.sync_status.value if final_detection is not None else None,
                },
                "alert_delivery": {
                    "remote_unique_alerts": len(server.state.alert_unique_ids),
                    "remote_alert_posts": server.state.alert_posts,
                },
            }

    _write_json(report_path, report)
    print(f"Evidence report: {report_path}")
    print(
        "Remote sync baseline: "
        f"first_run_failed={report['sync_transport']['first_run_failed']}, "
        f"retry_run_synced={report['sync_transport']['retry_run_synced']}, "
        f"idempotent_replay_synced={report['sync_transport']['idempotent_replay_synced']}"
    )
    print(
        "Alert delivery baseline: "
        f"remote_unique_alerts={report['alert_delivery']['remote_unique_alerts']}, "
        f"remote_alert_posts={report['alert_delivery']['remote_alert_posts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
