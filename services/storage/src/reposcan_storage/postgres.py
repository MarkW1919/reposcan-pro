"""PostgreSQL-backed storage repository with a sqlite test mode."""

from __future__ import annotations

import json
import sqlite3
from threading import RLock
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from reposcan_contracts.alert import AlertRecord, AlertStatus
from reposcan_contracts.detection import DetectionRecord
from reposcan_contracts.hotlist import HotlistEntry
from reposcan_contracts.review import ReviewRecord


ModelT = TypeVar("ModelT", bound=BaseModel)


class PostgresDriverUnavailableError(RuntimeError):
    pass


class PostgresStorageRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connection: Any | None = None,
        dialect: Literal["postgres", "sqlite"] = "postgres",
    ) -> None:
        self.dsn = dsn
        self.dialect = dialect
        self._lock = RLock()
        self._connection = connection or self._connect(dsn, dialect=dialect)
        if self.dialect == "sqlite" and hasattr(self._connection, "row_factory"):
            self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def _connect(self, dsn: str, *, dialect: Literal["postgres", "sqlite"]) -> Any:
        if dialect == "sqlite":
            connection = sqlite3.connect(dsn)
            connection.row_factory = sqlite3.Row
            return connection

        try:
            import psycopg
        except ImportError as exc:
            raise PostgresDriverUnavailableError(
                "psycopg is required to use the postgres storage backend; install RepoScan Pro with postgres support"
            ) from exc

        connection = psycopg.connect(dsn)
        connection.autocommit = True
        return connection

    def _sql(self, query: str) -> str:
        if self.dialect == "sqlite":
            return query.replace("%s", "?")
        return query

    def _execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        cursor = self._connection.cursor()
        cursor.execute(self._sql(query), params)
        if self.dialect == "sqlite":
            self._connection.commit()
        return cursor

    def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> Any | None:
        cursor = self._execute(query, params)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        cursor = self._execute(query, params)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def _initialize_schema(self) -> None:
        ddl_statements = []
        if self.dialect == "postgres":
            ddl_statements.append("CREATE EXTENSION IF NOT EXISTS postgis;")

        payload_type = "JSONB" if self.dialect == "postgres" else "TEXT"
        ddl_statements.extend(
            [
                f"""
                CREATE TABLE IF NOT EXISTS detections (
                    detection_id TEXT PRIMARY KEY,
                    camera_id TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    payload_json {payload_type} NOT NULL
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_detections_camera_timestamp
                ON detections (camera_id, timestamp_utc DESC);
                """,
                f"""
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    detection_id TEXT NOT NULL,
                    reviewed_at_utc TEXT NOT NULL,
                    payload_json {payload_type} NOT NULL
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_reviews_detection_timestamp
                ON reviews (detection_id, reviewed_at_utc DESC);
                """,
                f"""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    detection_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    payload_json {payload_type} NOT NULL
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_alerts_camera_timestamp
                ON alerts (camera_id, timestamp_utc DESC);
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_alerts_status_timestamp
                ON alerts (status, timestamp_utc DESC);
                """,
                f"""
                CREATE TABLE IF NOT EXISTS hotlists (
                    entry_id TEXT PRIMARY KEY,
                    active INTEGER NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    payload_json {payload_type} NOT NULL
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_hotlists_active_updated
                ON hotlists (active, updated_at_utc DESC);
                """,
            ]
        )
        for statement in ddl_statements:
            cursor = self._execute(statement)
            cursor.close()

    def _deserialize(self, model_type: type[ModelT], payload: Any) -> ModelT:
        if isinstance(payload, (dict, list)):
            data = payload
        else:
            data = json.loads(payload)
        return model_type.model_validate(data)

    def list_detections(self, *, camera_id: str | None = None, limit: int = 100) -> list[DetectionRecord]:
        with self._lock:
            if camera_id is None:
                rows = self._fetchall(
                    "SELECT payload_json FROM detections ORDER BY timestamp_utc DESC LIMIT %s",
                    (limit,),
                )
            else:
                rows = self._fetchall(
                    "SELECT payload_json FROM detections WHERE camera_id = %s ORDER BY timestamp_utc DESC LIMIT %s",
                    (camera_id, limit),
                )
        return [self._deserialize(DetectionRecord, row[0]) for row in rows]

    def get_detection(self, detection_id: str) -> DetectionRecord | None:
        with self._lock:
            row = self._fetchone(
                "SELECT payload_json FROM detections WHERE detection_id = %s",
                (detection_id,),
            )
        if row is None:
            return None
        return self._deserialize(DetectionRecord, row[0])

    def upsert_detection(self, detection: DetectionRecord) -> DetectionRecord:
        payload = json.dumps(detection.model_dump(mode="json"))
        with self._lock:
            cursor = self._execute(
                """
                INSERT INTO detections (detection_id, camera_id, timestamp_utc, payload_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(detection_id) DO UPDATE SET
                    camera_id = excluded.camera_id,
                    timestamp_utc = excluded.timestamp_utc,
                    payload_json = excluded.payload_json
                """,
                (detection.detection_id, detection.camera_id, detection.timestamp_utc, payload),
            )
            cursor.close()
        return detection

    def create_review(self, review: ReviewRecord) -> ReviewRecord:
        payload = json.dumps(review.model_dump(mode="json"))
        with self._lock:
            cursor = self._execute(
                """
                INSERT INTO reviews (review_id, detection_id, reviewed_at_utc, payload_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(review_id) DO UPDATE SET
                    detection_id = excluded.detection_id,
                    reviewed_at_utc = excluded.reviewed_at_utc,
                    payload_json = excluded.payload_json
                """,
                (review.review_id, review.detection_id, review.reviewed_at_utc, payload),
            )
            cursor.close()
        return review

    def list_reviews(self, detection_id: str) -> list[ReviewRecord]:
        with self._lock:
            rows = self._fetchall(
                "SELECT payload_json FROM reviews WHERE detection_id = %s ORDER BY reviewed_at_utc DESC",
                (detection_id,),
            )
        return [self._deserialize(ReviewRecord, row[0]) for row in rows]

    def list_alerts(
        self,
        *,
        camera_id: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if camera_id is not None:
            clauses.append("camera_id = %s")
            params.append(camera_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status.value if isinstance(status, AlertStatus) else status)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        query = f"SELECT payload_json FROM alerts {where_clause} ORDER BY timestamp_utc DESC LIMIT %s"
        with self._lock:
            rows = self._fetchall(query, tuple(params))
        return [self._deserialize(AlertRecord, row[0]) for row in rows]

    def get_alert(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            row = self._fetchone(
                "SELECT payload_json FROM alerts WHERE alert_id = %s",
                (alert_id,),
            )
        if row is None:
            return None
        return self._deserialize(AlertRecord, row[0])

    def create_alert(self, alert: AlertRecord) -> AlertRecord:
        payload = json.dumps(alert.model_dump(mode="json"))
        with self._lock:
            cursor = self._execute(
                """
                INSERT INTO alerts (alert_id, detection_id, camera_id, status, timestamp_utc, payload_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(alert_id) DO UPDATE SET
                    detection_id = excluded.detection_id,
                    camera_id = excluded.camera_id,
                    status = excluded.status,
                    timestamp_utc = excluded.timestamp_utc,
                    payload_json = excluded.payload_json
                """,
                (
                    alert.alert_id,
                    alert.detection_id,
                    alert.camera_id,
                    alert.status.value if isinstance(alert.status, AlertStatus) else alert.status,
                    alert.timestamp_utc,
                    payload,
                ),
            )
            cursor.close()
        return alert

    def list_hotlists(self, *, active_only: bool = False, limit: int = 100) -> list[HotlistEntry]:
        with self._lock:
            if active_only:
                rows = self._fetchall(
                    "SELECT payload_json FROM hotlists WHERE active = %s ORDER BY updated_at_utc DESC LIMIT %s",
                    (1 if self.dialect == "sqlite" else True, limit),
                )
            else:
                rows = self._fetchall(
                    "SELECT payload_json FROM hotlists ORDER BY updated_at_utc DESC LIMIT %s",
                    (limit,),
                )
        return [self._deserialize(HotlistEntry, row[0]) for row in rows]

    def get_hotlist(self, entry_id: str) -> HotlistEntry | None:
        with self._lock:
            row = self._fetchone(
                "SELECT payload_json FROM hotlists WHERE entry_id = %s",
                (entry_id,),
            )
        if row is None:
            return None
        return self._deserialize(HotlistEntry, row[0])

    def upsert_hotlist(self, entry: HotlistEntry) -> HotlistEntry:
        payload = json.dumps(entry.model_dump(mode="json"))
        active_value = entry.active if self.dialect == "postgres" else (1 if entry.active else 0)
        with self._lock:
            cursor = self._execute(
                """
                INSERT INTO hotlists (entry_id, active, updated_at_utc, payload_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(entry_id) DO UPDATE SET
                    active = excluded.active,
                    updated_at_utc = excluded.updated_at_utc,
                    payload_json = excluded.payload_json
                """,
                (entry.entry_id, active_value, entry.updated_at_utc, payload),
            )
            cursor.close()
        return entry
