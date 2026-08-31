"""Bounded background recording for continuously managed camera streams."""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Protocol

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FrameWriter(Protocol):
    def isOpened(self) -> bool: ...

    def write(self, frame: np.ndarray) -> None: ...

    def release(self) -> None: ...


class WriterFactory(Protocol):
    def __call__(
        self,
        path: Path,
        fps: float,
        frame_size: tuple[int, int],
    ) -> FrameWriter: ...


@dataclass(frozen=True, slots=True)
class RecordingSnapshot:
    state: str
    segments_completed: int
    dropped_frames: int
    error: str | None


@dataclass(frozen=True, slots=True)
class SegmentManifest:
    segment_id: str
    camera_id: str
    source_key: str
    filename: str
    started_at: str
    completed_at: str
    source_start_seconds: float
    source_end_seconds: float
    frame_count: int
    fps: float
    width: int
    height: int


@dataclass(slots=True)
class _ActiveSegment:
    writer: FrameWriter
    partial_path: Path
    final_path: Path
    segment_id: str
    source_key: str
    source_started_at: float
    wall_started_at: datetime
    width: int
    height: int
    frame_count: int = 0
    source_ended_at: float = 0


def _opencv_writer(
    path: Path,
    fps: float,
    frame_size: tuple[int, int],
) -> FrameWriter:
    return cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        frame_size,
    )


class BackgroundSegmentRecorder:
    """Write rotating MP4 segments away from the capture/inference thread."""

    def __init__(
        self,
        *,
        enabled: bool,
        camera_id: str,
        output_directory: Path,
        fps: float,
        segment_seconds: float,
        retention_hours: float,
        maximum_bytes: int,
        queue_size: int = 120,
        writer_factory: WriterFactory = _opencv_writer,
        on_segment: Callable[[Path, SegmentManifest], None] | None = None,
    ) -> None:
        if fps <= 0 or segment_seconds <= 0 or retention_hours <= 0:
            raise ValueError("Recording FPS, segment duration, and retention must be positive.")
        if maximum_bytes <= 0 or queue_size <= 0:
            raise ValueError("Recording byte and queue limits must be positive.")
        self._enabled = enabled
        self._camera_id = camera_id
        self._directory = (output_directory / camera_id).expanduser().resolve()
        self._fps = fps
        self._segment_seconds = segment_seconds
        self._retention_hours = retention_hours
        self._maximum_bytes = maximum_bytes
        self._writer_factory = writer_factory
        self._on_segment = on_segment
        self._queue: queue.Queue[tuple[np.ndarray, float] | None] = queue.Queue(queue_size)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._state = "disabled" if not enabled else "starting"
        self._segments_completed = 0
        self._dropped_frames = 0
        self._error: str | None = None
        self._segment_sequence = 0

    def __enter__(self) -> BackgroundSegmentRecorder:
        if not self._enabled:
            return self
        self._directory.mkdir(parents=True, exist_ok=True)
        self._state = "recording"
        self._thread = threading.Thread(
            target=self._run,
            name=f"continuous-recording-{self._camera_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def submit(self, frame: np.ndarray, timestamp_seconds: float) -> None:
        if not self._enabled or self._error is not None:
            return
        try:
            self._queue.put_nowait((frame.copy(), timestamp_seconds))
        except queue.Full:
            with self._lock:
                self._dropped_frames += 1

    def snapshot(self) -> RecordingSnapshot:
        with self._lock:
            return RecordingSnapshot(
                state=self._state,
                segments_completed=self._segments_completed,
                dropped_frames=self._dropped_frames,
                error=self._error,
            )

    def close(self) -> None:
        if self._thread is None:
            return
        if self._thread.is_alive():
            while True:
                try:
                    self._queue.put_nowait(None)
                    break
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        continue
                    with self._lock:
                        self._dropped_frames += 1
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            with self._lock:
                self._state = "error"
                self._error = "Recording thread did not stop within 30 seconds"
            logger.error(self._error)
        elif self._error is None:
            with self._lock:
                self._state = "stopped"
        self._thread = None

    def _run(self) -> None:
        active: _ActiveSegment | None = None
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                frame, timestamp_seconds = item
                if (
                    active is None
                    or timestamp_seconds - active.source_started_at >= self._segment_seconds
                    or frame.shape[1] != active.width
                    or frame.shape[0] != active.height
                ):
                    if active is not None:
                        completed = active
                        active = None
                        self._finalize(completed)
                    active = self._start_segment(frame, timestamp_seconds)
                active.writer.write(frame)
                active.frame_count += 1
                active.source_ended_at = timestamp_seconds
        except Exception as exc:
            logger.exception("Continuous recording failed: camera=%s", self._camera_id)
            with self._lock:
                self._state = "error"
                self._error = str(exc)
        finally:
            if active is not None:
                try:
                    self._finalize(active)
                except Exception as exc:
                    logger.exception("Could not finalize recording segment")
                    with self._lock:
                        self._state = "error"
                        self._error = str(exc)

    def _start_segment(self, frame: np.ndarray, timestamp_seconds: float) -> _ActiveSegment:
        wall_started_at = datetime.now(UTC)
        segment_id = str(uuid.uuid4())
        self._segment_sequence += 1
        stem = f"{wall_started_at:%Y%m%dT%H%M%S.%fZ}-{self._segment_sequence:06d}"
        final_path = self._directory / f"{stem}.mp4"
        partial_path = self._directory / f"{stem}.partial.mp4"
        height, width = frame.shape[:2]
        writer = self._writer_factory(partial_path, self._fps, (width, height))
        if not writer.isOpened():
            writer.release()
            raise RuntimeError(f"Could not open continuous recording segment {partial_path.name}")
        return _ActiveSegment(
            writer=writer,
            partial_path=partial_path,
            final_path=final_path,
            segment_id=segment_id,
            source_key=stem,
            source_started_at=timestamp_seconds,
            wall_started_at=wall_started_at,
            width=width,
            height=height,
            source_ended_at=timestamp_seconds,
        )

    def _finalize(self, segment: _ActiveSegment) -> None:
        segment.writer.release()
        segment.partial_path.replace(segment.final_path)
        duration_seconds = max(0.0, segment.source_ended_at - segment.source_started_at)
        completed_at = segment.wall_started_at + timedelta(seconds=duration_seconds)
        manifest = SegmentManifest(
            segment_id=segment.segment_id,
            camera_id=self._camera_id,
            source_key=segment.source_key,
            filename=segment.final_path.name,
            started_at=segment.wall_started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            source_start_seconds=segment.source_started_at,
            source_end_seconds=segment.source_ended_at,
            frame_count=segment.frame_count,
            fps=self._fps,
            width=segment.width,
            height=segment.height,
        )
        manifest_path = segment.final_path.with_suffix(".json")
        temporary_manifest = manifest_path.with_suffix(".json.partial")
        temporary_manifest.write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_manifest.replace(manifest_path)
        with self._lock:
            self._segments_completed += 1
        if self._on_segment is not None:
            self._on_segment(segment.final_path, manifest)
        self._enforce_retention(completed_at)

    def _enforce_retention(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=self._retention_hours)
        segments = sorted(self._directory.glob("*.mp4"), key=lambda path: path.stat().st_mtime)
        retained: list[Path] = []
        for path in segments:
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified < cutoff:
                self._delete_segment(path)
            else:
                retained.append(path)
        total_bytes = sum(path.stat().st_size for path in retained if path.exists())
        for path in retained:
            if total_bytes <= self._maximum_bytes:
                break
            if not path.exists():
                continue
            size = path.stat().st_size
            self._delete_segment(path)
            total_bytes -= size

    @staticmethod
    def _delete_segment(path: Path) -> None:
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)
