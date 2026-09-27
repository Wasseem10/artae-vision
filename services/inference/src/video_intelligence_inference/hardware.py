"""Dependency-light edge hardware and offline-queue discovery."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import cv2

from video_intelligence_inference import __version__


def _memory_mb() -> int:
    if hasattr(os, "sysconf"):
        try:
            pages = int(os.sysconf("SC_PHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return max(0, pages * page_size // (1024 * 1024))
        except (OSError, TypeError, ValueError):
            pass
    return 0


def collect_edge_profile(
    outbox_path: Path,
    evidence_outbox_path: Path | None = None,
    incident_clips_directory: Path | None = None,
) -> dict[str, object]:
    outbox_storage_mb = _free_storage_mb(outbox_path.parent)
    event_queue_depth = _outbox_depth(outbox_path)
    evidence_queue_depth = (
        _outbox_depth(evidence_outbox_path) if evidence_outbox_path is not None else 0
    )
    if evidence_outbox_path is not None:
        outbox_storage_mb = min(outbox_storage_mb, _free_storage_mb(evidence_outbox_path.parent))
    clips_directory_ready = (
        incident_clips_directory is not None and incident_clips_directory.is_dir()
    )
    incident_clips_storage_mb = (
        _free_storage_mb(incident_clips_directory) if clips_directory_ready else 0
    )
    storage_mb = (
        min(outbox_storage_mb, incident_clips_storage_mb)
        if incident_clips_directory is not None
        else outbox_storage_mb
    )
    queue_depth_known = event_queue_depth is not None and evidence_queue_depth is not None
    queue_depth = (event_queue_depth or 0) + (evidence_queue_depth or 0)
    try:
        cuda_devices = cv2.cuda.getCudaEnabledDeviceCount()
    except (AttributeError, cv2.error):
        cuda_devices = 0
    accelerator = (
        f"CUDA ({cuda_devices} device{'s' if cuda_devices != 1 else ''})" if cuda_devices else None
    )
    health = (
        "degraded" if storage_mb < 1024 or queue_depth > 100 or not queue_depth_known else "healthy"
    )
    return {
        "hostname": socket.gethostname(),
        "os_name": platform.system() or "unknown",
        "architecture": platform.machine() or "unknown",
        "cpu_count": os.cpu_count() or 1,
        "memory_mb": _memory_mb(),
        "accelerator": accelerator,
        "storage_available_mb": storage_mb,
        "worker_version": __version__,
        "health_status": health,
        "offline_queue_depth": queue_depth,
        "last_sync_at": (
            datetime.now(UTC).isoformat() if health == "healthy" and queue_depth == 0 else None
        ),
        "details": {
            "python": platform.python_version(),
            "event_queue_depth": event_queue_depth,
            "evidence_queue_depth": evidence_queue_depth,
            "queue_depth_known": queue_depth_known,
            "outbox_storage_available_mb": outbox_storage_mb,
            "incident_clips_storage_available_mb": (
                incident_clips_storage_mb if incident_clips_directory is not None else None
            ),
            "incident_clips_directory_ready": clips_directory_ready,
        },
    }


def _outbox_depth(path: Path) -> int | None:
    """Read an existing outbox without creating or repairing it during health sampling."""
    try:
        if (
            not path.is_file()
            or not os.access(path, os.W_OK)
            or not os.access(path.parent, os.W_OK)
        ):
            return None
        uri = path.resolve().as_uri() + "?mode=rw"
        with sqlite3.connect(uri, uri=True, timeout=0.25) as connection:
            row = connection.execute("SELECT COUNT(*) FROM event_outbox").fetchone()
        return int(row[0]) if row else None
    except (OSError, sqlite3.Error, ValueError):
        return None


def _free_storage_mb(directory: Path) -> int:
    try:
        return max(0, shutil.disk_usage(directory).free // (1024 * 1024))
    except OSError:
        return 0
