import json
from pathlib import Path

import numpy as np
import pytest
from video_intelligence_inference import events as events_module
from video_intelligence_inference.events import (
    EventRecord,
    EvidenceRecorder,
    JsonlEventSink,
)
from video_intelligence_inference.rules import RuleMatch


class FakeWriter:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []
        self.released = False

    def isOpened(self) -> bool:
        return True

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())

    def release(self) -> None:
        self.released = True


def make_event(tmp_path: Path, event_id: str = "event-1") -> EventRecord:
    match = RuleMatch(
        rule_id="person-dwell",
        track_id=7,
        object_class="person",
        zone_name="loading-zone",
        entered_at_seconds=0,
        occurred_at_seconds=5,
        dwell_seconds=5,
        confidence=0.91,
    )
    return EventRecord.create(
        match,
        camera_id="camera-1",
        clip_path=tmp_path / "clips" / f"{event_id}.mp4",
        event_id=event_id,
    )


def test_jsonl_sink_writes_one_structured_event(tmp_path: Path) -> None:
    event = make_event(tmp_path)
    sink = JsonlEventSink(tmp_path / "events.jsonl")

    sink.write(event)

    payload = json.loads(sink.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["event_type"] == "object_dwell"
    assert payload["track_id"] == 7
    assert payload["clip_path"].endswith("event-1.mp4")


def test_evidence_recorder_includes_pre_and_post_event_frames(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    writer = FakeWriter()
    monkeypatch.setattr(events_module.cv2, "VideoWriter_fourcc", lambda *args: 123)
    monkeypatch.setattr(events_module.cv2, "VideoWriter", lambda *args: writer)
    recorder = EvidenceRecorder(
        output_directory=tmp_path / "clips",
        fps=1,
        pre_event_seconds=2,
        post_event_seconds=1,
    )
    frame = np.zeros((20, 30, 3), dtype=np.uint8)

    recorder.process_frame(frame, timestamp_seconds=0, new_events=[])
    event = make_event(tmp_path)
    recorder.process_frame(frame, timestamp_seconds=1, new_events=[event])
    recorder.process_frame(frame, timestamp_seconds=1.5, new_events=[])
    completed = recorder.process_frame(frame, timestamp_seconds=2.1, new_events=[])

    assert len(completed) == 1
    assert completed[0].event_id == "event-1"
    assert completed[0].frame_count == 3
    assert len(writer.frames) == 3
    assert writer.released
    assert recorder.close() == []
