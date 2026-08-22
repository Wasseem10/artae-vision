"""Video-source abstraction for webcams, files, and RTSP streams."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Raised when a video source cannot be opened or read."""


class EndOfStream(SourceError):
    """Signals a normal end for a finite video file."""


@dataclass(frozen=True, slots=True)
class VideoFrame:
    image: np.ndarray
    timestamp_seconds: float
    sequence: int


class OpenCVVideoSource:
    """Own one OpenCV capture for `webcam:N`, a file path, or an RTSP URL."""

    def __init__(
        self,
        source: str,
        *,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
    ) -> None:
        self._source = source
        self._display_name = _redact_source(source)
        self._width = width
        self._height = height
        self._requested_fps = fps
        self._capture: cv2.VideoCapture | None = None
        self._live = False
        self._sequence = 0
        self._started_at = 0.0
        self._fps = float(fps)

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def is_live(self) -> bool:
        return self._live

    def open(self) -> None:
        if self._capture is not None:
            return

        capture_target, live = _resolve_capture_target(self._source)
        logger.info("Opening video source: %s", self._display_name)
        capture = cv2.VideoCapture(capture_target)
        if not capture.isOpened():
            capture.release()
            raise SourceError(
                f"Could not open video source '{self._display_name}'. Check the path, "
                "camera permissions, RTSP address, and credentials."
            )

        if live:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            capture.set(cv2.CAP_PROP_FPS, self._requested_fps)

        reported_fps = float(capture.get(cv2.CAP_PROP_FPS))
        self._fps = reported_fps if reported_fps > 0 else float(self._requested_fps)
        self._capture = capture
        self._live = live
        self._sequence = 0
        self._started_at = time.monotonic()
        logger.info("Video source opened: live=%s fps=%.2f", live, self._fps)

    def read(self) -> VideoFrame:
        if self._capture is None:
            raise SourceError("Video source must be opened before reading frames.")

        success, image = self._capture.read()
        if not success or image is None:
            if self._live:
                raise SourceError(f"Lost live video source '{self._display_name}'.")
            raise EndOfStream(f"Reached the end of '{self._display_name}'.")

        if self._live:
            timestamp = time.monotonic() - self._started_at
        else:
            reported_seconds = float(self._capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            fallback_seconds = self._sequence / self._fps
            timestamp = reported_seconds if reported_seconds > 0 else fallback_seconds

        packet = VideoFrame(image=image, timestamp_seconds=timestamp, sequence=self._sequence)
        self._sequence += 1
        return packet

    def close(self) -> None:
        if self._capture is None:
            return
        self._capture.release()
        self._capture = None
        logger.info("Video source closed: %s", self._display_name)

    def __enter__(self) -> OpenCVVideoSource:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _resolve_capture_target(source: str) -> tuple[int | str, bool]:
    normalized = source.strip()
    if normalized.lower().startswith("webcam:"):
        index_text = normalized.split(":", maxsplit=1)[1]
        try:
            index = int(index_text)
        except ValueError as exc:
            raise SourceError(f"Invalid webcam source '{source}'. Use webcam:0.") from exc
        if index < 0:
            raise SourceError("Webcam index must be zero or greater.")
        return index, True

    if normalized.lower().startswith(("rtsp://", "rtsps://")):
        return normalized, True

    path = Path(normalized).expanduser().resolve()
    if not path.is_file():
        raise SourceError(f"Video file does not exist: {path}")
    return str(path), False


def _redact_source(source: str) -> str:
    """Hide embedded RTSP credentials before a source reaches logs or errors."""
    normalized = source.strip()
    if normalized.lower().startswith(("rtsp://", "rtsps://")) and "@" in normalized:
        scheme, remainder = normalized.split("://", maxsplit=1)
        host_and_path = remainder.rsplit("@", maxsplit=1)[1]
        return f"{scheme}://***:***@{host_and_path}"
    return normalized
