import cv2
import numpy as np
from video_intelligence_inference.camera_diagnostics import diagnose_camera_stream


class FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self.frames = frames
        self.opened_with: str | int | None = None
        self.released = False

    def set(self, _key: int, _value: float) -> None:
        pass

    def open(self, source: str | int) -> bool:
        self.opened_with = source
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self) -> None:
        self.released = True


def test_diagnostics_measure_frames_without_loading_a_model() -> None:
    frames = []
    for index in range(12):
        frame = np.full((480, 640, 3), 90 + index, dtype=np.uint8)
        cv2.line(frame, (0, index * 10), (639, 479 - index * 10), (255, 255, 255), 4)
        frames.append(frame)
    capture = FakeCapture(frames)
    ticks = iter([0.0, *[index / 10 for index in range(12)], 1.2])

    output = diagnose_camera_stream(
        source_uri="webcam:3",
        duration_seconds=2,
        maximum_frames=12,
        capture_factory=lambda: capture,  # type: ignore[arg-type]
        monotonic=lambda: next(ticks),
    )

    assert capture.opened_with == 3
    assert capture.released is True
    assert output.metrics.frame_count == 12
    assert output.metrics.width == 640
    assert output.metrics.height == 480
    assert output.metrics.black_frame_ratio == 0
    assert output.preview_jpeg.startswith(b"\xff\xd8")
