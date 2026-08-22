"""Structured event records and bounded evidence-clip recording."""

from __future__ import annotations

import json
import logging
import math
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from video_intelligence_inference.rules import RuleMatch

logger = logging.getLogger(__name__)


class EvidenceError(RuntimeError):
    """Raised when an evidence clip cannot be encoded."""


class FrameWriter(Protocol):
    def isOpened(self) -> bool: ...

    def write(self, frame: np.ndarray) -> None: ...

    def release(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EventRecord:
    schema_version: int
    id: str
    event_type: str
    rule_id: str
    camera_id: str
    track_id: int | None
    object_class: str
    zone_name: str
    entered_at_seconds: float
    occurred_at_seconds: float
    dwell_seconds: float
    confidence: float
    occurred_at: str
    clip_path: str
    details: dict[str, object] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        match: RuleMatch,
        *,
        camera_id: str,
        clip_path: Path,
        event_id: str | None = None,
    ) -> EventRecord:
        return cls(
            schema_version=2,
            id=event_id or str(uuid.uuid4()),
            event_type=match.event_type,
            rule_id=match.rule_id,
            camera_id=camera_id,
            track_id=match.track_id,
            object_class=match.object_class,
            zone_name=match.zone_name,
            entered_at_seconds=match.entered_at_seconds,
            occurred_at_seconds=match.occurred_at_seconds,
            dwell_seconds=match.dwell_seconds,
            confidence=match.confidence,
            occurred_at=datetime.now(UTC).isoformat(),
            clip_path=str(clip_path.resolve()),
            details=match.details,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class JsonlEventSink:
    """Append durable, machine-readable event records without requiring a database."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    @property
    def path(self) -> Path:
        return self._path

    def write(self, event: EventRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
            output.flush()
        logger.info("Event persisted: id=%s path=%s", event.id, self._path)


@dataclass(frozen=True, slots=True)
class CompletedEvidence:
    event_id: str
    path: Path
    frame_count: int


@dataclass(frozen=True, slots=True)
class _BufferedFrame:
    jpeg_bytes: bytes


@dataclass(slots=True)
class _ActiveClip:
    event_id: str
    path: Path
    deadline_seconds: float
    writer: FrameWriter
    frame_count: int


class EvidenceRecorder:
    """Keep a compressed pre-event buffer and stream post-event frames to MP4."""

    def __init__(
        self,
        *,
        output_directory: Path,
        fps: float,
        pre_event_seconds: float,
        post_event_seconds: float,
        jpeg_quality: int = 80,
    ) -> None:
        if fps <= 0:
            raise ValueError("Evidence FPS must be greater than zero.")
        if pre_event_seconds < 0 or post_event_seconds < 0:
            raise ValueError("Evidence durations cannot be negative.")
        if not 1 <= jpeg_quality <= 100:
            raise ValueError("JPEG quality must be between 1 and 100.")

        self._output_directory = output_directory.expanduser().resolve()
        self._output_directory.mkdir(parents=True, exist_ok=True)
        self._fps = fps
        self._post_event_seconds = post_event_seconds
        self._jpeg_quality = jpeg_quality
        buffer_frames = max(1, math.ceil(pre_event_seconds * fps) + 1)
        self._pre_buffer: deque[_BufferedFrame] = deque(maxlen=buffer_frames)
        self._active: dict[str, _ActiveClip] = {}

    def path_for(self, event_id: str) -> Path:
        return self._output_directory / f"{event_id}.mp4"

    def process_frame(
        self,
        frame: np.ndarray,
        *,
        timestamp_seconds: float,
        new_events: list[EventRecord],
    ) -> list[CompletedEvidence]:
        completed: list[CompletedEvidence] = []

        for event_id, active in list(self._active.items()):
            if timestamp_seconds > active.deadline_seconds:
                completed.append(self._finish(event_id))
            else:
                active.writer.write(frame)
                active.frame_count += 1

        self._pre_buffer.append(_BufferedFrame(self._encode_frame(frame)))

        for event in new_events:
            if event.id in self._active:
                continue
            clip_path = Path(event.clip_path)
            active = self._start_clip(
                event.id,
                clip_path,
                frame.shape,
                deadline_seconds=timestamp_seconds + self._post_event_seconds,
            )
            self._active[event.id] = active
            if self._post_event_seconds == 0:
                completed.append(self._finish(event.id))

        return completed

    def close(self) -> list[CompletedEvidence]:
        return [self._finish(event_id) for event_id in list(self._active)]

    def _start_clip(
        self,
        event_id: str,
        path: Path,
        frame_shape: tuple[int, ...],
        *,
        deadline_seconds: float,
    ) -> _ActiveClip:
        height, width = frame_shape[:2]
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self._fps,
            (width, height),
        )
        if not writer.isOpened():
            writer.release()
            raise EvidenceError(f"Could not create evidence clip at {path}.")

        frame_count = 0
        try:
            for buffered in self._pre_buffer:
                decoded = cv2.imdecode(
                    np.frombuffer(buffered.jpeg_bytes, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if decoded is None:
                    raise EvidenceError("Could not decode a buffered evidence frame.")
                writer.write(decoded)
                frame_count += 1
        except Exception:
            writer.release()
            raise

        logger.info("Evidence recording started: event=%s path=%s", event_id, path)
        return _ActiveClip(
            event_id=event_id,
            path=path,
            deadline_seconds=deadline_seconds,
            writer=writer,
            frame_count=frame_count,
        )

    def _finish(self, event_id: str) -> CompletedEvidence:
        active = self._active.pop(event_id)
        active.writer.release()
        logger.info(
            "Evidence recording completed: event=%s frames=%d path=%s",
            event_id,
            active.frame_count,
            active.path,
        )
        return CompletedEvidence(event_id, active.path, active.frame_count)

    def _encode_frame(self, frame: np.ndarray) -> bytes:
        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
        )
        if not success:
            raise EvidenceError("Could not encode a pre-event frame.")
        return encoded.tobytes()
