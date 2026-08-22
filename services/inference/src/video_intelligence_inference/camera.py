import logging
from types import TracebackType

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when the webcam cannot be opened or read."""


class WebcamCamera:
    """Own the lifecycle of one local OpenCV webcam."""

    def __init__(self, index: int, width: int, height: int, fps: int) -> None:
        self._index = index
        self._width = width
        self._height = height
        self._fps = fps
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._capture is not None:
            return

        logger.info("Opening webcam", extra={"camera_index": self._index})
        capture = cv2.VideoCapture(self._index)
        if not capture.isOpened():
            capture.release()
            raise CameraError(
                f"Could not open webcam index {self._index}. "
                "Check camera permissions and whether another app is using it."
            )

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        capture.set(cv2.CAP_PROP_FPS, self._fps)
        self._capture = capture

        actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = capture.get(cv2.CAP_PROP_FPS)
        logger.info(
            "Webcam opened: index=%d resolution=%dx%d fps=%.1f",
            self._index,
            actual_width,
            actual_height,
            actual_fps,
        )

    def read(self) -> np.ndarray:
        if self._capture is None:
            raise CameraError("Camera must be opened before reading frames.")

        success, frame = self._capture.read()
        if not success or frame is None:
            raise CameraError(f"Failed to read a frame from webcam index {self._index}.")
        return frame

    def close(self) -> None:
        if self._capture is None:
            return

        self._capture.release()
        self._capture = None
        logger.info("Webcam closed", extra={"camera_index": self._index})

    def __enter__(self) -> "WebcamCamera":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
