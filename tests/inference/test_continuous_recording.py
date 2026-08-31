import json
from pathlib import Path

import numpy as np
from video_intelligence_inference.continuous_recording import BackgroundSegmentRecorder


class FakeWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.write_bytes(b"")
        self.released = False

    def isOpened(self) -> bool:
        return True

    def write(self, _frame: np.ndarray) -> None:
        with self.path.open("ab") as output:
            output.write(b"f")

    def release(self) -> None:
        self.released = True


def fake_writer(path: Path, _fps: float, _size: tuple[int, int]) -> FakeWriter:
    return FakeWriter(path)


def test_continuous_recorder_rotates_atomic_segments_and_writes_manifests(
    tmp_path: Path,
) -> None:
    frame = np.zeros((12, 20, 3), dtype=np.uint8)
    recorder = BackgroundSegmentRecorder(
        enabled=True,
        camera_id="camera-1",
        output_directory=tmp_path,
        fps=5,
        segment_seconds=1,
        retention_hours=24,
        maximum_bytes=1000,
        queue_size=10,
        writer_factory=fake_writer,
    )

    with recorder:
        recorder.submit(frame, 0)
        recorder.submit(frame, 0.5)
        recorder.submit(frame, 1.1)

    snapshot = recorder.snapshot()
    segments = sorted((tmp_path / "camera-1").glob("*.mp4"))
    manifests = sorted((tmp_path / "camera-1").glob("*.json"))

    assert snapshot.state == "stopped"
    assert snapshot.segments_completed == 2
    assert snapshot.dropped_frames == 0
    assert len(segments) == 2
    assert len(manifests) == 2
    assert not list((tmp_path / "camera-1").glob("*.partial*"))
    assert sum(json.loads(path.read_text())["frame_count"] for path in manifests) == 3


def test_continuous_recorder_enforces_total_byte_retention(tmp_path: Path) -> None:
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    recorder = BackgroundSegmentRecorder(
        enabled=True,
        camera_id="camera-2",
        output_directory=tmp_path,
        fps=1,
        segment_seconds=1,
        retention_hours=24,
        maximum_bytes=2,
        queue_size=10,
        writer_factory=fake_writer,
    )

    with recorder:
        recorder.submit(frame, 0)
        recorder.submit(frame, 1)
        recorder.submit(frame, 2)

    segments = sorted((tmp_path / "camera-2").glob("*.mp4"))
    assert len(segments) == 2
    assert sum(path.stat().st_size for path in segments) <= 2
    assert len(list((tmp_path / "camera-2").glob("*.json"))) == 2


def test_disabled_continuous_recorder_does_not_touch_disk(tmp_path: Path) -> None:
    recorder = BackgroundSegmentRecorder(
        enabled=False,
        camera_id="camera-3",
        output_directory=tmp_path,
        fps=1,
        segment_seconds=1,
        retention_hours=1,
        maximum_bytes=1,
    )
    with recorder:
        recorder.submit(np.zeros((2, 2, 3), dtype=np.uint8), 0)

    assert recorder.snapshot().state == "disabled"
    assert not (tmp_path / "camera-3").exists()
