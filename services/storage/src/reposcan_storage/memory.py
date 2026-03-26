"""In-memory repository implementation for tests and local wiring."""

from __future__ import annotations

from threading import RLock

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.dispatch import DispatchAssignmentRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord, FollowUpStatus
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorSessionRecord
from reposcan_contracts.review import ReviewRecord


class InMemoryStorageRepository:
    def __init__(self) -> None:
        self._detections: dict[str, DetectionRecord] = {}
        self._follow_ups: dict[str, FollowUpRecord] = {}
        self._assignments: dict[str, DispatchAssignmentRecord] = {}
        self._reviews: list[ReviewRecord] = []
        self._alerts: dict[str, AlertRecord] = {}
        self._hotlists: dict[str, HotlistEntry] = {}
        self._sessions: dict[str, OperatorSessionRecord] = {}
        self._lock = RLock()

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        with self._lock:
            detections = sorted(
                self._detections.values(),
                key=lambda record: record.timestamp_utc,
                reverse=True,
            )
        if camera_id is not None:
            detections = [record for record in detections if record.camera_id == camera_id]
        return detections[:limit]

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        with self._lock:
            return self._detections.get(detection_id)

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        with self._lock:
            self._detections[detection.detection_id] = detection
        return detection

    def list_follow_ups(
        self,
        *,
        detection_id: str | None = None,
        status: FollowUpStatus | None = None,
        limit: int = 100,
    ) -> list[FollowUpRecord]:
        with self._lock:
            follow_ups = sorted(self._follow_ups.values(), key=lambda record: record.updated_at_utc, reverse=True)
        if detection_id is not None:
            follow_ups = [record for record in follow_ups if record.detection_id == detection_id]
        if status is not None:
            follow_ups = [record for record in follow_ups if record.status == status]
        return follow_ups[:limit]

    def get_follow_up(self, follow_up_id: str) -> FollowUpRecord | None:
        with self._lock:
            return self._follow_ups.get(follow_up_id)

    def upsert_follow_up(self, follow_up: FollowUpRecord) -> FollowUpRecord:
        with self._lock:
            self._follow_ups[follow_up.follow_up_id] = follow_up
        return follow_up

    def list_assignments(
        self,
        *,
        detection_id: str | None = None,
        limit: int = 100,
    ) -> list[DispatchAssignmentRecord]:
        with self._lock:
            assignments = sorted(self._assignments.values(), key=lambda record: record.updated_at_utc, reverse=True)
        if detection_id is not None:
            assignments = [record for record in assignments if record.detection_id == detection_id]
        return assignments[:limit]

    def get_assignment(self, assignment_id: str) -> DispatchAssignmentRecord | None:
        with self._lock:
            return self._assignments.get(assignment_id)

    def upsert_assignment(self, assignment: DispatchAssignmentRecord) -> DispatchAssignmentRecord:
        with self._lock:
            self._assignments[assignment.assignment_id] = assignment
        return assignment

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        with self._lock:
            self._reviews.append(review)
        return review

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        with self._lock:
            return sorted(
                [review for review in self._reviews if review.detection_id == detection_id],
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
            alerts = sorted(
                self._alerts.values(),
                key=lambda record: record.timestamp_utc,
                reverse=True,
            )
        if camera_id is not None:
            alerts = [record for record in alerts if record.camera_id == camera_id]
        if status is not None:
            alerts = [record for record in alerts if record.status == status]
        return alerts[:limit]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            self._alerts[alert.alert_id] = alert
        return alert

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        with self._lock:
            entries = sorted(
                self._hotlists.values(),
                key=lambda record: record.updated_at_utc,
                reverse=True,
            )
        if active_only:
            entries = [record for record in entries if record.active]
        return entries[:limit]

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        with self._lock:
            return self._hotlists.get(entry_id)

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        with self._lock:
            self._hotlists[entry.entry_id] = entry
        return entry

    def list_operator_sessions(self, *, limit: int = 100) -> list[OperatorSessionRecord]:
        with self._lock:
            sessions = sorted(self._sessions.values(), key=lambda record: record.last_seen_at_utc, reverse=True)
        return sessions[:limit]

    def upsert_operator_session(self, session: OperatorSessionRecord) -> OperatorSessionRecord:
        with self._lock:
            self._sessions[session.session_id] = session
        return session
