from pathlib import Path

from video_intelligence_inference.hardware import collect_edge_profile
from video_intelligence_inference.outbox import DurableJsonOutbox


def test_edge_profile_discovers_hardware_and_offline_queue(tmp_path: Path) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    outbox = DurableJsonOutbox(outbox_path)
    outbox.put("event-1", {"id": "event-1"})

    profile = collect_edge_profile(outbox_path)

    assert profile["hostname"]
    assert profile["os_name"]
    assert profile["architecture"]
    assert profile["cpu_count"] >= 1
    assert profile["storage_available_mb"] >= 0
    assert profile["worker_version"] == "0.7.0"
    assert profile["offline_queue_depth"] == 1
    assert profile["last_sync_at"] is None
