"""JSON-backed repository for the Phase 2 storage skeleton.

This keeps the persistence surface local-first and file-backed while the later
Postgres adapter is introduced. The repository contract is intentionally small
so it can be replaced without disturbing API handlers.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import TypeVar

from pydantic import BaseModel

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.dispatch import DispatchAssignmentRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord, FollowUpStatus
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorSessionRecord
from reposcan_contracts.review import ReviewRecord

ModelT = TypeVar("ModelT", bound=BaseModel)


class JsonFileStorageRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._detections_path = self.root / "detections.json"
        self._follow_ups_path = self.root / "follow_ups.json"
        self._assignments_path = self.root / "assignments.json"
        self._reviews_path = self.root / "reviews.json"
        self._alerts_path = self.root / "alerts.json"
        self._hotlists_path = self.root / "hotlists.json"
        self._sessions_path = self.root / "sessions.json"
        self._lock = RLock()
        self._ensure_file(self._detections_path)
        self._ensure_file(self._follow_ups_path)
        self._ensure_file(self._assignments_path)
        self._ensure_file(self._reviews_path)
        self._ensure_file(self._alerts_path)
        self._ensure_file(self._hotlists_path)
        self._ensure_file(self._sessions_path)

    def _backup_path(self, path: Path) -> Path:
        return path.with_suffix(f"{path.suffix}.bak")

    def _temp_path(self, path: Path) -> Path:
        return path.with_suffix(f"{path.suffix}.tmp")

    def _load_payload(self, path: Path) -> list[object]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} does not contain a list payload")
        return payload

    def _restore_from(self, source: Path, destination: Path) -> bool:
        try:
            self._load_payload(source)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    def _ensure_file(self, path: Path) -> None:
        backup = self._backup_path(path)
        temp = self._temp_path(path)

        if path.exists():
            try:
                self._load_payload(path)
                return
            except (OSError, ValueError, json.JSONDecodeError):
                if self._restore_from(temp, path) or self._restore_from(backup, path):
                    return
        else:
            if self._restore_from(temp, path) or self._restore_from(backup, path):
                return

        path.write_text("[]\n", encoding="utf-8")

    def _read_records(self, path: Path, model_type: type[ModelT]) -> list[ModelT]:
        payload = self._load_payload(path)
        return [model_type.model_validate(item) for item in payload]

    def _write_records(self, path: Path, records: list[BaseModel]) -> None:
        payload = [record.model_dump(mode="json") for record in records]
        temp_path = self._temp_path(path)
        backup_path = self._backup_path(path)
        temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if path.exists():
            path.replace(backup_path)
        temp_path.replace(path)
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        with self._lock:
            detections = self._read_records(self._detections_path, DetectionRecord)
        detections = sorted(detections, key=lambda record: record.timestamp_utc, reverse=True)
        if camera_id is not None:
            detections = [record for record in detections if record.camera_id == camera_id]
        return detections[:limit]

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        with self._lock:
            detections = self._read_records(self._detections_path, DetectionRecord)
        for detection in detections:
            if detection.detection_id == detection_id:
                return detection
        return None

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        with self._lock:
            detections = self._read_records(self._detections_path, DetectionRecord)
            by_id = {record.detection_id: record for record in detections}
            by_id[detection.detection_id] = detection
            ordered = sorted(by_id.values(), key=lambda record: record.timestamp_utc, reverse=True)
            self._write_records(self._detections_path, ordered)
        return detection

    def list_follow_ups(
        self,
        *,
        detection_id: str | None = None,
        status: FollowUpStatus | None = None,
        limit: int = 100,
    ) -> list[FollowUpRecord]:
        with self._lock:
            follow_ups = self._read_records(self._follow_ups_path, FollowUpRecord)
        follow_ups = sorted(follow_ups, key=lambda record: record.updated_at_utc, reverse=True)
        if detection_id is not None:
            follow_ups = [record for record in follow_ups if record.detection_id == detection_id]
        if status is not None:
            follow_ups = [record for record in follow_ups if record.status == status]
        return follow_ups[:limit]

    def get_follow_up(self, follow_up_id: str) -> FollowUpRecord | None:
        with self._lock:
            follow_ups = self._read_records(self._follow_ups_path, FollowUpRecord)
        for follow_up in follow_ups:
            if follow_up.follow_up_id == follow_up_id:
                return follow_up
        return None

    def upsert_follow_up(self, follow_up: FollowUpRecord) -> FollowUpRecord:
        with self._lock:
            follow_ups = self._read_records(self._follow_ups_path, FollowUpRecord)
            by_id = {record.follow_up_id: record for record in follow_ups}
            by_id[follow_up.follow_up_id] = follow_up
            ordered = sorted(by_id.values(), key=lambda record: record.updated_at_utc, reverse=True)
            self._write_records(self._follow_ups_path, ordered)
        return follow_up

    def list_assignments(
        self,
        *,
        detection_id: str | None = None,
        limit: int = 100,
    ) -> list[DispatchAssignmentRecord]:
        with self._lock:
            assignments = self._read_records(self._assignments_path, DispatchAssignmentRecord)
        assignments = sorted(assignments, key=lambda record: record.updated_at_utc, reverse=True)
        if detection_id is not None:
            assignments = [record for record in assignments if record.detection_id == detection_id]
        return assignments[:limit]

    def get_assignment(self, assignment_id: str) -> DispatchAssignmentRecord | None:
        with self._lock:
            assignments = self._read_records(self._assignments_path, DispatchAssignmentRecord)
        for assignment in assignments:
            if assignment.assignment_id == assignment_id:
                return assignment
        return None

    def upsert_assignment(self, assignment: DispatchAssignmentRecord) -> DispatchAssignmentRecord:
        with self._lock:
            assignments = self._read_records(self._assignments_path, DispatchAssignmentRecord)
            by_id = {record.assignment_id: record for record in assignments}
            by_id[assignment.assignment_id] = assignment
            ordered = sorted(by_id.values(), key=lambda record: record.updated_at_utc, reverse=True)
            self._write_records(self._assignments_path, ordered)
        return assignment

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        with self._lock:
            reviews = self._read_records(self._reviews_path, ReviewRecord)
            reviews.append(review)
            self._write_records(self._reviews_path, reviews)
        return review

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        with self._lock:
            reviews = self._read_records(self._reviews_path, ReviewRecord)
        return sorted(
            [review for review in reviews if review.detection_id == detection_id],
            key=lambda record: record.reviewed_at_utc,
            reverse=True,
        )

    def list_alerts(
        self,
        *,
        camera_id: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        with self._lock:
            alerts = self._read_records(self._alerts_path, AlertRecord)
        alerts = sorted(alerts, key=lambda record: record.timestamp_utc, reverse=True)
        if camera_id is not None:
            alerts = [record for record in alerts if record.camera_id == camera_id]
        if status is not None:
            alerts = [record for record in alerts if record.status == status]
        return alerts[:limit]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            alerts = self._read_records(self._alerts_path, AlertRecord)
        for alert in alerts:
            if alert.alert_id == alert_id:
                return alert
        return None

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            alerts = self._read_records(self._alerts_path, AlertRecord)
            by_id = {record.alert_id: record for record in alerts}
            by_id[alert.alert_id] = alert
            ordered = sorted(by_id.values(), key=lambda record: record.timestamp_utc, reverse=True)
            self._write_records(self._alerts_path, ordered)
        return alert

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
        entries = sorted(entries, key=lambda record: record.updated_at_utc, reverse=True)
        if active_only:
            entries = [record for record in entries if record.active]
        return entries[:limit]

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
            by_id = {record.entry_id: record for record in entries}
            by_id[entry.entry_id] = entry
            ordered = sorted(by_id.values(), key=lambda record: record.updated_at_utc, reverse=True)
            self._write_records(self._hotlists_path, ordered)
        return entry

    def delete_hotlist(self, entry_id: str) -> bool:
        with self._lock:
            entries = self._read_records(self._hotlists_path, HotlistEntry)
            remaining = [entry for entry in entries if entry.entry_id != entry_id]
            if len(remaining) == len(entries):
                return False
            ordered = sorted(remaining, key=lambda record: record.updated_at_utc, reverse=True)
            self._write_records(self._hotlists_path, ordered)
        return True

    def list_operator_sessions(self, *, limit: int = 100) -> list[OperatorSessionRecord]:
        with self._lock:
            sessions = self._read_records(self._sessions_path, OperatorSessionRecord)
        sessions = sorted(sessions, key=lambda record: record.last_seen_at_utc, reverse=True)
        return sessions[:limit]

    def upsert_operator_session(self, session: OperatorSessionRecord) -> OperatorSessionRecord:
        with self._lock:
            sessions = self._read_records(self._sessions_path, OperatorSessionRecord)
            by_id = {record.session_id: record for record in sessions}
            by_id[session.session_id] = session
            ordered = sorted(by_id.values(), key=lambda record: record.last_seen_at_utc, reverse=True)
            self._write_records(self._sessions_path, ordered)
        return session
