import sqlite3
from pathlib import Path
from types import SimpleNamespace

from video_intelligence_inference import hardware
from video_intelligence_inference.hardware import collect_edge_profile
from video_intelligence_inference.outbox import DurableJsonOutbox


def test_edge_profile_discovers_hardware_and_offline_queue(tmp_path: Path) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    outbox = DurableJsonOutbox(outbox_path)
    outbox.put("event-1", {"id": "event-1"})
    evidence_outbox_path = tmp_path / "offline" / "evidence.db"
    DurableJsonOutbox(evidence_outbox_path).put("event-1", {"path": "event.mp4"})
    incident_clips_directory = tmp_path / "events" / "clips"
    incident_clips_directory.mkdir(parents=True)

    profile = collect_edge_profile(
        outbox_path, evidence_outbox_path, incident_clips_directory
    )

    assert profile["hostname"]
    assert profile["os_name"]
    assert profile["architecture"]
    assert profile["cpu_count"] >= 1
    assert profile["storage_available_mb"] >= 0
    assert profile["worker_version"] == "0.7.0"
    assert profile["offline_queue_depth"] == 2
    assert profile["details"]["event_queue_depth"] == 1
    assert profile["details"]["evidence_queue_depth"] == 1
    assert profile["details"]["queue_depth_known"] is True
    assert profile["details"]["outbox_storage_available_mb"] >= 0
    assert profile["details"]["incident_clips_storage_available_mb"] >= 0
    assert profile["details"]["incident_clips_directory_ready"] is True
    assert profile["last_sync_at"] is None


def test_edge_profile_degrades_for_low_incident_clip_volume(
    tmp_path: Path, monkeypatch
) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    incident_clips_directory = tmp_path / "other-volume" / "clips"
    incident_clips_directory.mkdir(parents=True)
    mebibyte = 1024 * 1024

    def disk_usage(directory: Path) -> SimpleNamespace:
        free_mb = 600 if directory == incident_clips_directory else 4096
        return SimpleNamespace(free=free_mb * mebibyte)

    monkeypatch.setattr(hardware.shutil, "disk_usage", disk_usage)

    profile = collect_edge_profile(
        outbox_path, incident_clips_directory=incident_clips_directory
    )

    assert profile["health_status"] == "degraded"
    assert profile["storage_available_mb"] == 600
    assert profile["details"]["outbox_storage_available_mb"] == 4096
    assert profile["details"]["incident_clips_storage_available_mb"] == 600
    assert profile["details"]["evidence_queue_depth"] == 0


def test_edge_profile_checks_separate_evidence_outbox_volume(
    tmp_path: Path, monkeypatch
) -> None:
    outbox_path = tmp_path / "event-volume" / "events.db"
    evidence_outbox_path = tmp_path / "evidence-volume" / "evidence.db"
    incident_clips_directory = tmp_path / "clip-volume" / "clips"
    incident_clips_directory.mkdir(parents=True)
    mebibyte = 1024 * 1024

    def disk_usage(directory: Path) -> SimpleNamespace:
        free_mb = 700 if directory == evidence_outbox_path.parent else 4096
        return SimpleNamespace(free=free_mb * mebibyte)

    monkeypatch.setattr(hardware.shutil, "disk_usage", disk_usage)

    profile = collect_edge_profile(
        outbox_path, evidence_outbox_path, incident_clips_directory
    )

    assert profile["health_status"] == "degraded"
    assert profile["storage_available_mb"] == 700
    assert profile["details"]["outbox_storage_available_mb"] == 700
    assert profile["details"]["incident_clips_storage_available_mb"] == 4096


def test_edge_profile_degrades_when_incident_clip_directory_is_missing(
    tmp_path: Path,
) -> None:
    profile = collect_edge_profile(
        tmp_path / "offline" / "events.db",
        incident_clips_directory=tmp_path / "unmounted" / "clips",
    )

    assert profile["health_status"] == "degraded"
    assert profile["storage_available_mb"] == 0
    assert profile["details"]["incident_clips_storage_available_mb"] == 0
    assert profile["details"]["incident_clips_directory_ready"] is False


def test_edge_profile_marks_missing_outbox_depth_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        hardware.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=4096 * 1024 * 1024),
    )
    clips = tmp_path / "clips"
    clips.mkdir()

    profile = collect_edge_profile(
        tmp_path / "missing.db", incident_clips_directory=clips
    )

    assert profile["health_status"] == "degraded"
    assert profile["details"]["event_queue_depth"] is None
    assert profile["details"]["queue_depth_known"] is False
    assert profile["last_sync_at"] is None
    assert not (tmp_path / "missing.db").exists()


def test_edge_profile_marks_read_only_outbox_depth_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        hardware.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=4096 * 1024 * 1024),
    )
    outbox_path = tmp_path / "events.db"
    DurableJsonOutbox(outbox_path)
    real_access = hardware.os.access

    def read_only_access(path: Path, mode: int) -> bool:
        return path != outbox_path and real_access(path, mode)

    monkeypatch.setattr(hardware.os, "access", read_only_access)
    profile = collect_edge_profile(outbox_path)

    assert profile["health_status"] == "degraded"
    assert profile["details"]["event_queue_depth"] is None
    assert profile["details"]["queue_depth_known"] is False


def test_edge_profile_marks_corrupt_outbox_depth_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        hardware.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=4096 * 1024 * 1024),
    )
    outbox_path = tmp_path / "events.db"
    outbox_path.write_text("not a SQLite database")

    profile = collect_edge_profile(outbox_path)

    assert profile["health_status"] == "degraded"
    assert profile["details"]["event_queue_depth"] is None
    assert profile["details"]["queue_depth_known"] is False


def test_edge_profile_marks_locked_outbox_depth_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        hardware.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=4096 * 1024 * 1024),
    )
    outbox_path = tmp_path / "events.db"
    with sqlite3.connect(outbox_path) as setup:
        setup.execute("CREATE TABLE event_outbox (record_id TEXT PRIMARY KEY)")
    with sqlite3.connect(outbox_path) as lock:
        lock.execute("BEGIN EXCLUSIVE")
        profile = collect_edge_profile(outbox_path)
        lock.rollback()

    assert profile["health_status"] == "degraded"
    assert profile["details"]["event_queue_depth"] is None
    assert profile["details"]["queue_depth_known"] is False


def test_edge_profile_degrades_with_full_outbox_volume(
    tmp_path: Path, monkeypatch
) -> None:
    outbox_path = tmp_path / "offline" / "events.db"
    DurableJsonOutbox(outbox_path)
    clips = tmp_path / "clips"
    clips.mkdir()

    def disk_usage(directory: Path) -> SimpleNamespace:
        free_mb = 0 if directory == outbox_path.parent else 4096
        return SimpleNamespace(free=free_mb * 1024 * 1024)

    monkeypatch.setattr(hardware.shutil, "disk_usage", disk_usage)

    profile = collect_edge_profile(outbox_path, incident_clips_directory=clips)

    assert profile["health_status"] == "degraded"
    assert profile["storage_available_mb"] == 0
    assert profile["details"]["event_queue_depth"] == 0
    assert profile["details"]["queue_depth_known"] is True
    assert profile["last_sync_at"] is None
