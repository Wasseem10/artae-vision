from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from video_intelligence_inference import source as source_module
from video_intelligence_inference.source import (
    EndOfStream,
    OpenCVVideoSource,
    SourceError,
)


class FakeCapture:
    def __init__(self, frames: list[np.ndarray], *, opened: bool = True) -> None:
        self.frames = iter(frames)
        self.opened = opened
        self.released = False
        self.set_calls: list[tuple[int, Any]] = []
        self.position_ms = 0.0

    def isOpened(self) -> bool:
        return self.opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        try:
            frame = next(self.frames)
        except StopIteration:
            return False, None
        self.position_ms += 40
        return True, frame

    def get(self, property_id: int) -> float:
        if property_id == cv2.CAP_PROP_FPS:
            return 25.0
        if property_id == cv2.CAP_PROP_POS_MSEC:
            return self.position_ms
        return 0.0

    def set(self, property_id: int, value: Any) -> bool:
        self.set_calls.append((property_id, value))
        return True

    def release(self) -> None:
        self.released = True


def test_file_source_emits_timestamps_and_normal_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"placeholder")
    frame = np.zeros((20, 30, 3), dtype=np.uint8)
    capture = FakeCapture([frame])
    monkeypatch.setattr(source_module.cv2, "VideoCapture", lambda target: capture)

    with OpenCVVideoSource(str(video_path)) as source:
        packet = source.read()
        assert packet.sequence == 0
        assert packet.timestamp_seconds == pytest.approx(0.04)
        with pytest.raises(EndOfStream):
            source.read()

    assert capture.released


def test_webcam_source_applies_requested_capture_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakeCapture([np.zeros((10, 10, 3), dtype=np.uint8)])
    targets: list[int | str] = []

    def make_capture(target: int | str) -> FakeCapture:
        targets.append(target)
        return capture

    monkeypatch.setattr(source_module.cv2, "VideoCapture", make_capture)
    with OpenCVVideoSource("webcam:2", width=640, height=360, fps=15) as source:
        assert source.is_live
        source.read()

    assert targets == [2]
    assert capture.set_calls == [
        (cv2.CAP_PROP_FRAME_WIDTH, 640),
        (cv2.CAP_PROP_FRAME_HEIGHT, 360),
        (cv2.CAP_PROP_FPS, 15),
    ]


def test_invalid_source_is_rejected() -> None:
    with pytest.raises(SourceError, match="does not exist"):
        OpenCVVideoSource("missing-video.mp4").open()


def test_rtsp_credentials_are_redacted_from_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakeCapture([], opened=False)
    monkeypatch.setattr(source_module.cv2, "VideoCapture", lambda target: capture)
    source = OpenCVVideoSource("rtsp://camera-user:super-secret@10.0.0.5/live")

    with pytest.raises(SourceError) as error:
        source.open()

    message = str(error.value)
    assert "super-secret" not in message
    assert "camera-user" not in message
    assert "rtsp://***:***@10.0.0.5/live" in message


def test_live_source_recovers_after_a_bounded_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = np.full((12, 16, 3), 7, dtype=np.uint8)
    captures = [FakeCapture([]), FakeCapture([frame])]
    delays: list[float] = []

    monkeypatch.setattr(
        source_module.cv2,
        "VideoCapture",
        lambda *_args: captures.pop(0),
    )
    with OpenCVVideoSource(
        "rtsp://camera.test/live",
        reconnect_attempts=2,
        reconnect_backoff_seconds=0.25,
        sleep=delays.append,
    ) as source:
        packet = source.read()

        assert packet.sequence == 0
        assert packet.image is frame
        assert source.reconnect_count == 1

    assert delays == [0.25]


def test_live_source_fails_after_reconnect_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = [
        FakeCapture([]),
        FakeCapture([], opened=False),
        FakeCapture([], opened=False),
    ]
    monkeypatch.setattr(
        source_module.cv2,
        "VideoCapture",
        lambda *_args: captures.pop(0),
    )
    source = OpenCVVideoSource(
        "rtsp://user:secret@camera.test/live",
        reconnect_attempts=2,
        reconnect_backoff_seconds=0,
    )

    with source, pytest.raises(SourceError, match="after 2 reconnect attempt") as error:
        source.read()

    assert "secret" not in str(error.value)
