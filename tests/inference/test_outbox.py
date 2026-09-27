"""Cross-dispatcher leases for the durable camera-event queue."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from video_intelligence_inference.outbox import DurableJsonOutbox


def test_two_outbox_instances_cannot_claim_the_same_event(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    first = DurableJsonOutbox(path)
    second = DurableJsonOutbox(path)
    first.put("event-1", {"id": "event-1"})
    barrier = Barrier(3)

    def claim(outbox: DurableJsonOutbox, owner: str) -> list[str]:
        barrier.wait()
        return [
            record.record_id
            for record in outbox.claim_pending(owner, lease_seconds=10, now=100)
        ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        one = executor.submit(claim, first, "worker-1")
        two = executor.submit(claim, second, "worker-2")
        barrier.wait()
        assert sorted((one.result(timeout=2), two.result(timeout=2))) == [
            [],
            ["event-1"],
        ]


def test_crashed_owner_expires_and_stale_ack_cannot_delete_new_claim(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.db"
    crashed = DurableJsonOutbox(path)
    recovered = DurableJsonOutbox(path)
    crashed.put("event-1", {"id": "event-1"})

    assert [
        record.record_id
        for record in crashed.claim_pending("dead-worker", lease_seconds=10, now=100)
    ] == ["event-1"]
    assert recovered.claim_pending("new-worker", lease_seconds=10, now=109) == []
    assert [
        record.record_id
        for record in recovered.claim_pending("new-worker", lease_seconds=10, now=110)
    ] == ["event-1"]
    assert not crashed.acknowledge("event-1", owner_id="dead-worker")
    assert recovered.count() == 1
    assert recovered.acknowledge("event-1", owner_id="new-worker")
    assert recovered.count() == 0


def test_existing_outbox_schema_migrates_without_losing_events(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE event_outbox (
                record_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO event_outbox (record_id, payload_json) VALUES (?, ?)",
            ("event-1", json.dumps({"id": "event-1"})),
        )

    outbox = DurableJsonOutbox(path)
    claimed = outbox.claim_pending("new-worker", lease_seconds=10, now=100)
    assert [record.payload for record in claimed] == [{"id": "event-1"}]
    assert outbox.acknowledge("event-1", owner_id="new-worker")
    assert outbox.count() == 0
