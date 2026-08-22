"""Process-local latest-frame store used by the native dashboard fallback."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreviewFrame:
    organization_id: str
    jpeg: bytes
    received_at: float


class PreviewStore:
    """Keep only the newest bounded JPEG for each camera."""

    def __init__(self) -> None:
        self._frames: dict[str, PreviewFrame] = {}
        self._lock = asyncio.Lock()

    async def put(self, camera_id: str, organization_id: str, jpeg: bytes) -> None:
        async with self._lock:
            self._frames[camera_id] = PreviewFrame(
                organization_id=organization_id,
                jpeg=jpeg,
                received_at=time.monotonic(),
            )

    async def get(self, camera_id: str, *, max_age_seconds: float) -> PreviewFrame | None:
        async with self._lock:
            frame = self._frames.get(camera_id)
            if frame is None:
                return None
            if time.monotonic() - frame.received_at > max_age_seconds:
                self._frames.pop(camera_id, None)
                return None
            return frame
