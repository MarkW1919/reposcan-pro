"""Repository interfaces for local metadata persistence."""

from __future__ import annotations

from typing import Protocol

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.dispatch import DispatchAssignmentRecord
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.followup import FollowUpRecord, FollowUpStatus
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.operator import OperatorSessionRecord
from reposcan_contracts.review import ReviewRecord


class StorageRepository(Protocol):
    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        ...

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        ...

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        ...

    def list_follow_ups(
        self,
        *,
        detection_id: str | None = None,
        status: FollowUpStatus | None = None,
        limit: int = 100,
    ) -> list[FollowUpRecord]:
        ...

    def get_follow_up(self, follow_up_id: str) -> FollowUpRecord | None:
        ...

    def upsert_follow_up(self, follow_up: FollowUpRecord) -> FollowUpRecord:
        ...

    def list_assignments(
        self,
        *,
        detection_id: str | None = None,
        limit: int = 100,
    ) -> list[DispatchAssignmentRecord]:
        ...

    def get_assignment(self, assignment_id: str) -> DispatchAssignmentRecord | None:
        ...

    def upsert_assignment(self, assignment: DispatchAssignmentRecord) -> DispatchAssignmentRecord:
        ...

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        ...

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        ...

    def list_alerts(
        self,
        *,
        camera_id: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        ...

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        ...

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        ...

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        ...

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        ...

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        ...

    def delete_hotlist(self, entry_id: str) -> bool:
        ...

    def list_operator_sessions(self, *, limit: int = 100) -> list[OperatorSessionRecord]:
        ...

    def upsert_operator_session(self, session: OperatorSessionRecord) -> OperatorSessionRecord:
        ...
