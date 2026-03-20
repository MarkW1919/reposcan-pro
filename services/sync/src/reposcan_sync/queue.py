"""JSON-backed local sync queue."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from .models import SyncQueueItem


class JsonSyncQueue:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def _read(self) -> list[SyncQueueItem]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [SyncQueueItem.model_validate(item) for item in payload]

    def _write(self, items: list[SyncQueueItem]) -> None:
        payload = [item.model_dump(mode="json") for item in items]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def list_items(self) -> list[SyncQueueItem]:
        with self._lock:
            return self._read()

    def get_by_record(self, *, record_type: str, record_id: str) -> SyncQueueItem | None:
        with self._lock:
            for item in self._read():
                if item.record_type == record_type and item.record_id == record_id:
                    return item
        return None

    def upsert(self, item: SyncQueueItem) -> SyncQueueItem:
        with self._lock:
            items = self._read()
            by_id = {existing.queue_id: existing for existing in items}
            by_id[item.queue_id] = item
            self._write(sorted(by_id.values(), key=lambda entry: (entry.available_at_utc, entry.queue_id)))
        return item

    def remove(self, queue_id: str) -> None:
        with self._lock:
            items = [item for item in self._read() if item.queue_id != queue_id]
            self._write(items)
