from unittest.mock import Mock

import numpy as np
import pytest
from video_intelligence_inference.camera import CameraError, WebcamCamera


def test_camera_context_reads_frame_and_releases_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    fake_capture = Mock()
    fake_capture.isOpened.return_value = True
    fake_capture.read.return_value = (True, frame)
    fake_capture.get.return_value = 30.0
    monkeypatch.setattr(
        "video_intelligence_inference.camera.cv2.VideoCapture", lambda _: fake_capture
    )

    with WebcamCamera(index=0, width=1280, height=720, fps=30) as camera:
        assert camera.read() is frame

    fake_capture.release.assert_called_once()


def test_camera_raises_helpful_error_when_device_cannot_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_capture = Mock()
    fake_capture.isOpened.return_value = False
    monkeypatch.setattr(
        "video_intelligence_inference.camera.cv2.VideoCapture", lambda _: fake_capture
    )

    with pytest.raises(CameraError, match="Could not open webcam index 2"):
        WebcamCamera(index=2, width=640, height=480, fps=30).open()

    fake_capture.release.assert_called_once()
