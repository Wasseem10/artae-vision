"""Cross-dispatcher leases for the durable camera-event queue."""

from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
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


def test_evidence_retention_requires_durable_ack_and_protects_queued_clips(
    tmp_path: Path,
) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    pending = clips / "pending.mp4"
    pending.write_bytes(b"not accepted")
    accepted = clips / "accepted.mp4"
    accepted.write_bytes(b"accepted")
    untracked = clips / "untracked.mp4"
    untracked.write_bytes(b"never submitted")
    path = tmp_path / "evidence.db"
    first = DurableJsonOutbox(path)
    first.put("pending", {"path": str(pending)})
    first.put("accepted", {"path": str(accepted)})
    assert [r.record_id for r in first.claim_pending("uploader", lease_seconds=60)] == [
        "accepted"
    ]
    assert first.acknowledge_evidence("accepted", accepted, owner_id="uploader")

    # A new process can prune accepted evidence, but never infer acceptance from
    # the absence of a queue row for an arbitrary local clip.
    recovered = DurableJsonOutbox(path)
    assert recovered.prune_acknowledged_evidence(
        clips, retention_hours=1, now=time.time() + 3601
    ) == 1
    assert not accepted.exists()
    assert pending.read_bytes() == b"not accepted"
    assert untracked.read_bytes() == b"never submitted"
    assert recovered.count() == 1


def test_evidence_retention_protects_leased_paths_and_changed_files(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    clip = clips / "event-1.mp4"
    clip.write_bytes(b"accepted")
    outbox = DurableJsonOutbox(tmp_path / "evidence.db")
    outbox.put("event-1", {"path": str(clip)})
    outbox.claim_pending("uploader", lease_seconds=60)
    assert outbox.acknowledge_evidence("event-1", clip, owner_id="uploader")
    outbox.put("requeued-copy", {"path": str(clip)})
    outbox.claim_pending("other-uploader", lease_seconds=60)
    future = time.time() + 3601
    assert outbox.prune_acknowledged_evidence(clips, retention_hours=1, now=future) == 0
    assert clip.exists()

    outbox.acknowledge("requeued-copy", owner_id="other-uploader")
    clip.write_bytes(b"different source")
    assert outbox.prune_acknowledged_evidence(clips, retention_hours=1, now=future) == 0
    assert clip.read_bytes() == b"different source"


def test_evidence_retention_cleans_acknowledged_cache_after_restart(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    clip = clips / "event-1.mp4"
    clip.write_bytes(b"source")
    cache = clips / "event-1.upload.mp4"
    cache.write_bytes(b"transcoded")
    path = tmp_path / "evidence.db"
    outbox = DurableJsonOutbox(path)
    outbox.put("event-1", {"path": str(clip)})
    outbox.claim_pending("uploader", lease_seconds=60)
    assert outbox.acknowledge_evidence(
        "event-1", clip, owner_id="uploader", cache_path=cache
    )

    # A crash between deleting source and cache leaves the receipt for recovery.
    clip.unlink()
    restarted = DurableJsonOutbox(path)
    assert restarted.prune_acknowledged_evidence(
        clips, retention_hours=1, now=time.time() + 3601
    ) == 1
    assert not cache.exists()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM acknowledged_evidence").fetchone()[0] == 0


@pytest.mark.parametrize("invalid_payload", ["{not-json", '{"path":null}', "{}"])
def test_evidence_retention_fails_closed_on_malformed_pending_row(
    tmp_path: Path, invalid_payload: str
) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    clip = clips / "accepted.mp4"
    clip.write_bytes(b"accepted")
    path = tmp_path / "evidence.db"
    outbox = DurableJsonOutbox(path)
    outbox.put("accepted", {"path": str(clip)})
    outbox.claim_pending("uploader", lease_seconds=60)
    assert outbox.acknowledge_evidence("accepted", clip, owner_id="uploader")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO event_outbox (record_id, payload_json) VALUES (?, ?)",
            ("corrupt", invalid_payload),
        )

    with pytest.raises((json.JSONDecodeError, KeyError, ValueError)):
        outbox.prune_acknowledged_evidence(
            clips, retention_hours=1, now=time.time() + 3601
        )
    assert clip.read_bytes() == b"accepted"
