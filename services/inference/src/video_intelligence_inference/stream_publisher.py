"""Bounded raw-frame publisher for browser playback through MediaMTX."""

from __future__ import annotations

import logging
import queue
import subprocess
import threading
from contextlib import suppress
from types import TracebackType

import imageio_ffmpeg
import numpy as np

logger = logging.getLogger(__name__)


def build_raw_publish_command(
    ffmpeg: str,
    publish_url: str,
    *,
    width: int,
    height: int,
    fps: float,
) -> list[str]:
    """Build a shell-free FFmpeg command for BGR frames over standard input."""
    if not publish_url.lower().startswith(("rtsp://", "rtsps://")):
        raise ValueError("The browser stream publisher requires an RTSP URL")
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("Publisher dimensions and FPS must be positive")
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        f"{fps:.3f}",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(max(1, round(fps))),
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        publish_url,
    ]


class BackgroundFramePublisher:
    """Publish latest-only camera frames without blocking capture or inference."""

    def __init__(self, publish_url: str | None, *, fps: float, queue_size: int = 2) -> None:
        if queue_size < 1:
            raise ValueError("Publisher queue size must be positive")
        self._publish_url = publish_url
        self._fps = fps
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=queue_size)
        self._process: subprocess.Popen[bytes] | None = None
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None
        if publish_url:
            self._thread = threading.Thread(
                target=self._run,
                name="camera-stream-publisher",
                daemon=True,
            )
            self._thread.start()

    def submit(self, frame: np.ndarray) -> None:
        if not self._publish_url or self._error is not None:
            return
        frame_copy = np.ascontiguousarray(frame).copy()
        try:
            self._queue.put_nowait(frame_copy)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            self._queue.put_nowait(frame_copy)

    def close(self) -> None:
        if self._thread is None:
            return
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            self._queue.put_nowait(None)
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.warning("Camera stream publisher did not stop within ten seconds")

    def _run(self) -> None:
        try:
            while True:
                frame = self._queue.get()
                try:
                    if frame is None:
                        return
                    if self._process is None:
                        self._process = self._start_process(frame)
                    assert self._process.stdin is not None
                    self._process.stdin.write(frame.tobytes())
                    self._process.stdin.flush()
                finally:
                    self._queue.task_done()
        except (BrokenPipeError, OSError, ValueError) as error:
            self._error = error
            logger.exception("Browser stream publisher failed")
        finally:
            self._stop_process()

    def _start_process(self, frame: np.ndarray) -> subprocess.Popen[bytes]:
        height, width = frame.shape[:2]
        assert self._publish_url is not None
        command = build_raw_publish_command(
            imageio_ffmpeg.get_ffmpeg_exe(),
            self._publish_url,
            width=width,
            height=height,
            fps=self._fps,
        )
        logger.info("Publishing camera frames to the local browser stream gateway")
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

    def _stop_process(self) -> None:
        process = self._process
        if process is None:
            return
        if process.stdin is not None:
            with suppress(OSError):
                process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._process = None

    def __enter__(self) -> BackgroundFramePublisher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
