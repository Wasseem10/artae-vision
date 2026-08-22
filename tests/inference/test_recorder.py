from pathlib import Path
from typing import Self

import numpy as np
import pytest
from video_intelligence_inference import recorder


class FakeCamera:
    def __init__(self) -> None:
        self.frame = np.zeros((48, 64, 3), dtype=np.uint8)
        self.read_count = 0
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def read(self) -> np.ndarray:
        self.read_count += 1
        return self.frame.copy()


class FakeWriter:
    def __init__(self, opened: bool = True) -> None:
        self.opened = opened
        self.frames: list[np.ndarray] = []
        self.released = False

    def isOpened(self) -> bool:
        return self.opened

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame)

    def release(self) -> None:
        self.released = True


def test_record_clip_writes_expected_frames_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    camera = FakeCamera()
    writer = FakeWriter()
    monkeypatch.setattr(recorder.cv2, "VideoWriter_fourcc", lambda *args: 123)
    monkeypatch.setattr(recorder.cv2, "VideoWriter", lambda *args: writer)

    summary = recorder.record_clip(
        camera,  # type: ignore[arg-type]
        output_path=tmp_path / "nested" / "clip.mp4",
        duration_seconds=0.5,
        fps=10,
    )

    assert summary.frame_count == 5
    assert (summary.width, summary.height) == (64, 48)
    assert camera.read_count == 5
    assert camera.closed
    assert writer.released
    assert len(writer.frames) == 5
    assert (tmp_path / "nested").is_dir()


def test_record_clip_releases_failed_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    camera = FakeCamera()
    writer = FakeWriter(opened=False)
    monkeypatch.setattr(recorder.cv2, "VideoWriter_fourcc", lambda *args: 123)
    monkeypatch.setattr(recorder.cv2, "VideoWriter", lambda *args: writer)

    with pytest.raises(recorder.RecordingError):
        recorder.record_clip(
            camera,  # type: ignore[arg-type]
            output_path=tmp_path / "clip.mp4",
            duration_seconds=1,
            fps=1,
        )

    assert camera.closed
    assert writer.released
