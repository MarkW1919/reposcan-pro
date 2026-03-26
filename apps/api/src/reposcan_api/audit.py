"""Audit logging helpers for the API boundary."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from .models import ApiAuditEvent


class ApiAuditLogger:
    """Append-only JSONL audit log with simple readback filters."""

    def __init__(self, root: str | Path, *, enabled: bool = True, max_read_limit: int = 500) -> None:
        self.enabled = enabled
        self.root = Path(root)
        self.path = self.root / "events.jsonl"
        self.max_read_limit = max_read_limit
        self._lock = RLock()
        if self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path.touch(exist_ok=True)

    def record(self, event: ApiAuditEvent) -> None:
        if not self.enabled:
            return
        payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")

    def list_events(
        self,
        *,
        limit: int = 100,
        principal_id: str | None = None,
        action_prefix: str | None = None,
        outcome: str | None = None,
        target_id: str | None = None,
    ) -> list[ApiAuditEvent]:
        if not self.enabled or not self.path.exists():
            return []

        capped_limit = min(limit, self.max_read_limit)
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()

        events: list[ApiAuditEvent] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            event = ApiAuditEvent.model_validate_json(line)
            if principal_id is not None and event.principal_id != principal_id:
                continue
            if action_prefix is not None and not event.action.startswith(action_prefix):
                continue
            if outcome is not None and event.outcome.value != outcome:
                continue
            if target_id is not None and event.target_id != target_id:
                continue
            events.append(event)
            if len(events) >= capped_limit:
                break
        return events
