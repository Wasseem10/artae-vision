"""Small durable JSON outbox for camera events created while the cloud is unavailable."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    record_id: str
    payload: dict[str, object]
    attempts: int


class DurableJsonOutbox:
    """Persist idempotent event payloads until their HTTP receiver acknowledges them."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_outbox (
                    record_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def put(self, record_id: str, payload: dict[str, object]) -> None:
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO event_outbox (record_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(record_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (record_id, serialized),
            )

    def pending(self, limit: int = 100) -> list[OutboxRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, payload_json, attempts
                FROM event_outbox
                ORDER BY created_at, record_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            OutboxRecord(
                record_id=str(row[0]),
                payload=json.loads(str(row[1])),
                attempts=int(row[2]),
            )
            for row in rows
        ]

    def acknowledge(self, record_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM event_outbox WHERE record_id = ?", (record_id,))

    def fail(self, record_id: str, error: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE event_outbox
                SET attempts = attempts + 1, last_error = ?
                WHERE record_id = ?
                """,
                (error[:1000], record_id),
            )

    def count(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()
        return int(row[0]) if row else 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)
