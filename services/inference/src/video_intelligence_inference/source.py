"""Video-source abstraction for webcams, files, and RTSP streams."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
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
        open_timeout_seconds: float = 10.0,
        read_timeout_seconds: float = 10.0,
        reconnect_attempts: int = 5,
        reconnect_backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if open_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("Video-source timeouts must be greater than zero.")
        if reconnect_attempts < 0:
            raise ValueError("Reconnect attempts cannot be negative.")
        if reconnect_backoff_seconds < 0:
            raise ValueError("Reconnect backoff cannot be negative.")
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
        self._open_timeout_ms = round(open_timeout_seconds * 1000)
        self._read_timeout_ms = round(read_timeout_seconds * 1000)
        self._reconnect_attempts = reconnect_attempts
        self._reconnect_backoff_seconds = reconnect_backoff_seconds
        self._sleep = sleep
        self._reconnect_count = 0

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def is_live(self) -> bool:
        return self._live

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    def open(self) -> None:
        if self._capture is not None:
            return

        capture_target, live = _resolve_capture_target(self._source)
        logger.info("Opening video source: %s", self._display_name)
        capture = self._create_capture(capture_target, live)
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
        self._reconnect_count = 0
        logger.info("Video source opened: live=%s fps=%.2f", live, self._fps)

    def read(self) -> VideoFrame:
        if self._capture is None:
            raise SourceError("Video source must be opened before reading frames.")

        success, image = self._capture.read()
        if not success or image is None:
            if not self._live:
                raise EndOfStream(f"Reached the end of '{self._display_name}'.")
            image = self._recover_live_source()

        if self._live:
            timestamp = time.monotonic() - self._started_at
        else:
            reported_seconds = float(self._capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            fallback_seconds = self._sequence / self._fps
            timestamp = reported_seconds if reported_seconds > 0 else fallback_seconds

        packet = VideoFrame(image=image, timestamp_seconds=timestamp, sequence=self._sequence)
        self._sequence += 1
        return packet

    def _create_capture(self, target: int | str, live: bool) -> cv2.VideoCapture:
        if live and isinstance(target, str) and target.lower().startswith(("rtsp://", "rtsps://")):
            parameters = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                self._open_timeout_ms,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                self._read_timeout_ms,
            ]
            try:
                return cv2.VideoCapture(target, cv2.CAP_FFMPEG, parameters)
            except TypeError:
                # Older OpenCV builds do not expose constructor parameters. The
                # fallback remains compatible, but operators should use a build
                # with FFmpeg timeout support for production RTSP cameras.
                logger.warning("OpenCV build does not support RTSP timeout parameters")
        return cv2.VideoCapture(target)

    def _recover_live_source(self) -> np.ndarray:
        last_error = "read failed"
        for attempt in range(1, self._reconnect_attempts + 1):
            self.close()
            delay = min(self._reconnect_backoff_seconds * (2 ** (attempt - 1)), 10.0)
            if delay:
                self._sleep(delay)
            try:
                target, live = _resolve_capture_target(self._source)
                capture = self._create_capture(target, live)
                if not capture.isOpened():
                    capture.release()
                    raise SourceError("capture did not open")
                if live and isinstance(target, int):
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
                    capture.set(cv2.CAP_PROP_FPS, self._requested_fps)
                success, image = capture.read()
                if not success or image is None:
                    capture.release()
                    raise SourceError("capture reopened but produced no frame")
                reported_fps = float(capture.get(cv2.CAP_PROP_FPS))
                self._fps = reported_fps if reported_fps > 0 else float(self._requested_fps)
                self._capture = capture
                self._live = True
                self._reconnect_count += 1
                logger.warning(
                    "Live video source recovered: source=%s attempt=%d reconnects=%d",
                    self._display_name,
                    attempt,
                    self._reconnect_count,
                )
                return image
            except SourceError as exc:
                last_error = str(exc)
                logger.warning(
                    "Live video reconnect failed: source=%s attempt=%d/%d",
                    self._display_name,
                    attempt,
                    self._reconnect_attempts,
                )
        raise SourceError(
            f"Lost live video source '{self._display_name}' after "
            f"{self._reconnect_attempts} reconnect attempt(s): {last_error}"
        )

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
