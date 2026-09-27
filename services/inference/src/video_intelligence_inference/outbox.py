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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS acknowledged_evidence (
                    record_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    source_size INTEGER NOT NULL,
                    source_mtime_ns INTEGER NOT NULL,
                    cache_path TEXT,
                    cache_size INTEGER,
                    cache_mtime_ns INTEGER,
                    acknowledged_at REAL NOT NULL
                )
                """
            )
            receipt_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(acknowledged_evidence)")
            }
            for column in ("cache_path", "cache_size", "cache_mtime_ns"):
                if column not in receipt_columns:
                    column_type = "TEXT" if column == "cache_path" else "INTEGER"
                    connection.execute(
                        f"ALTER TABLE acknowledged_evidence ADD COLUMN {column} {column_type}"
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

    def acknowledge_evidence(
        self,
        record_id: str,
        source_path: Path,
        *,
        owner_id: str,
        cache_path: Path | None = None,
    ) -> bool:
        """Atomically remove a claimed upload and retain proof of its accepted source."""
        source = source_path.expanduser().resolve()
        source_stat = source.stat()
        cache = cache_path.expanduser().resolve() if cache_path is not None else None
        cache_stat = None
        if cache is not None:
            try:
                cache_stat = cache.stat()
            except FileNotFoundError:
                cache = None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM event_outbox WHERE record_id = ? AND lease_owner = ?",
                (record_id, owner_id),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                """
                INSERT INTO acknowledged_evidence (
                    record_id, source_path, source_size, source_mtime_ns,
                    cache_path, cache_size, cache_mtime_ns, acknowledged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    source_path = excluded.source_path,
                    source_size = excluded.source_size,
                    source_mtime_ns = excluded.source_mtime_ns,
                    cache_path = excluded.cache_path,
                    cache_size = excluded.cache_size,
                    cache_mtime_ns = excluded.cache_mtime_ns,
                    acknowledged_at = excluded.acknowledged_at
                """,
                (
                    record_id,
                    str(source),
                    source_stat.st_size,
                    source_stat.st_mtime_ns,
                    str(cache) if cache is not None else None,
                    cache_stat.st_size if cache_stat is not None else None,
                    cache_stat.st_mtime_ns if cache_stat is not None else None,
                    time.time(),
                ),
            )
        return True

    def prune_acknowledged_evidence(
        self, clips_directory: Path, *, retention_hours: float, now: float | None = None
    ) -> int:
        """Delete only old, unchanged ACKed source clips with no queued reference."""
        if not math.isfinite(retention_hours) or retention_hours <= 0:
            raise ValueError("Evidence retention must be finite and positive")
        cutoff = (time.time() if now is None else now) - retention_hours * 3600
        if not math.isfinite(cutoff):
            raise ValueError("Evidence retention time must be finite")
        clips_root = clips_directory.expanduser().resolve()
        removed = 0
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            # Include every row, regardless of retry time or lease owner.
            pending_rows = connection.execute("SELECT payload_json FROM event_outbox").fetchall()
            pending_paths: set[Path] = set()
            for row in pending_rows:
                path = json.loads(str(row[0]))["path"]
                if not isinstance(path, str) or not path or not Path(path).is_absolute():
                    raise ValueError("Evidence outbox has an invalid pending path")
                pending_paths.add(Path(path).expanduser().resolve())
            receipts = connection.execute(
                """
                SELECT record_id, source_path, source_size, source_mtime_ns,
                       cache_path, cache_size, cache_mtime_ns
                FROM acknowledged_evidence WHERE acknowledged_at <= ?
                """,
                (cutoff,),
            ).fetchall()
            for (
                record_id,
                raw_path,
                source_size,
                source_mtime_ns,
                raw_cache,
                cache_size,
                cache_mtime_ns,
            ) in receipts:
                source = Path(str(raw_path))
                if source.is_symlink():
                    continue
                resolved = source.resolve()
                if (
                    resolved.parent != clips_root
                    or resolved.name != f"{record_id}.mp4"
                    or resolved in pending_paths
                ):
                    continue
                paths = [(source, source_size, source_mtime_ns)]
                if raw_cache is not None:
                    cache = Path(str(raw_cache))
                    if cache.is_symlink():
                        continue
                    resolved_cache = cache.resolve()
                    if (
                        resolved_cache != resolved.with_name(f"{resolved.stem}.upload.mp4")
                        or resolved_cache in pending_paths
                    ):
                        continue
                    paths.append((cache, cache_size, cache_mtime_ns))
                existing: list[Path] = []
                changed = False
                for path, recorded_size, recorded_mtime_ns in paths:
                    try:
                        stat = path.stat()
                    except FileNotFoundError:
                        continue
                    if stat.st_size != recorded_size or stat.st_mtime_ns != recorded_mtime_ns:
                        changed = True
                        break
                    existing.append(path)
                if changed:
                    continue
                for path in existing:
                    path.unlink()
                connection.execute(
                    "DELETE FROM acknowledged_evidence WHERE record_id = ?", (record_id,)
                )
                removed += int(bool(existing))
        return removed

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
