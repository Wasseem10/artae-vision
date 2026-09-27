"""Small durable JSON outbox for camera events created while the cloud is unavailable."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
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
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_outbox (
                    record_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    next_attempt_at REAL
                )
                """
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(event_outbox)")}
            for column, column_type in (
                ("lease_owner", "TEXT"),
                ("lease_expires_at", "REAL"),
                ("next_attempt_at", "REAL"),
            ):
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE event_outbox ADD COLUMN {column} {column_type}"
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
        return self._records(rows)

    def claim_pending(
        self,
        owner_id: str,
        *,
        lease_seconds: float,
        limit: int = 1,
        now: float | None = None,
    ) -> list[OutboxRecord]:
        """Atomically lease due events across dispatchers and processes."""
        if not owner_id:
            raise ValueError("Outbox claim owner must be nonempty")
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Outbox lease duration must be finite and positive")
        if limit <= 0:
            raise ValueError("Outbox claim limit must be positive")
        claimed_at = time.time() if now is None else now
        if not math.isfinite(claimed_at):
            raise ValueError("Outbox claim time must be finite")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT record_id, payload_json, attempts
                FROM event_outbox
                WHERE (lease_expires_at IS NULL OR lease_expires_at <= ?)
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at, record_id
                LIMIT ?
                """,
                (claimed_at, claimed_at, limit),
            ).fetchall()
            connection.executemany(
                """
                UPDATE event_outbox
                SET lease_owner = ?, lease_expires_at = ?
                WHERE record_id = ?
                """,
                ((owner_id, claimed_at + lease_seconds, row[0]) for row in rows),
            )
        return self._records(rows)

    @staticmethod
    def _records(rows: list[tuple[object, ...]]) -> list[OutboxRecord]:
        return [
            OutboxRecord(
                record_id=str(row[0]),
                payload=json.loads(str(row[1])),
                attempts=int(row[2]),
            )
            for row in rows
        ]

    def acknowledge(self, record_id: str, *, owner_id: str | None = None) -> bool:
        with self._lock, self._connect() as connection:
            if owner_id is None:
                cursor = connection.execute(
                    "DELETE FROM event_outbox WHERE record_id = ?", (record_id,)
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM event_outbox WHERE record_id = ? AND lease_owner = ?",
                    (record_id, owner_id),
                )
        return cursor.rowcount == 1

    def renew_claim(self, record_id: str, owner_id: str, *, lease_seconds: float) -> bool:
        """Extend a long-running upload only while this owner still holds its claim."""
        if not owner_id:
            raise ValueError("Outbox claim owner must be nonempty")
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("Outbox lease duration must be finite and positive")
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE event_outbox
                SET lease_expires_at = ?
                WHERE record_id = ? AND lease_owner = ?
                """,
                (time.time() + lease_seconds, record_id, owner_id),
            )
        return cursor.rowcount == 1

    def fail(
        self,
        record_id: str,
        error: str,
        *,
        owner_id: str | None = None,
        retry_delay_seconds: float = 0.0,
    ) -> bool:
        if not math.isfinite(retry_delay_seconds) or retry_delay_seconds < 0:
            raise ValueError("Outbox retry delay must be finite and nonnegative")
        next_attempt_at = time.time() + retry_delay_seconds if retry_delay_seconds else None
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE event_outbox
                SET attempts = attempts + 1, last_error = ?,
                    lease_owner = NULL, lease_expires_at = NULL, next_attempt_at = ?
                WHERE record_id = ? AND (? IS NULL OR lease_owner = ?)
                """,
                (error[:1000], next_attempt_at, record_id, owner_id, owner_id),
            )
        return cursor.rowcount == 1

    def count(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()
        return int(row[0]) if row else 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)
