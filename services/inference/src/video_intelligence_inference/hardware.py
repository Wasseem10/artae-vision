"""Dependency-light edge hardware and offline-queue discovery."""

from __future__ import annotations

import os
import platform
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path

import cv2

from video_intelligence_inference import __version__
from video_intelligence_inference.outbox import DurableJsonOutbox


def _memory_mb() -> int:
    if hasattr(os, "sysconf"):
        try:
            pages = int(os.sysconf("SC_PHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return max(0, pages * page_size // (1024 * 1024))
        except (OSError, TypeError, ValueError):
            pass
    return 0


def collect_edge_profile(outbox_path: Path) -> dict[str, object]:
    outbox = DurableJsonOutbox(outbox_path)
    storage_mb = shutil.disk_usage(outbox_path.parent).free // (1024 * 1024)
    queue_depth = outbox.count()
    try:
        cuda_devices = cv2.cuda.getCudaEnabledDeviceCount()
    except (AttributeError, cv2.error):
        cuda_devices = 0
    accelerator = (
        f"CUDA ({cuda_devices} device{'s' if cuda_devices != 1 else ''})" if cuda_devices else None
    )
    health = "degraded" if storage_mb < 1024 or queue_depth > 100 else "healthy"
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
        "last_sync_at": datetime.now(UTC).isoformat() if queue_depth == 0 else None,
        "details": {"python": platform.python_version()},
    }
