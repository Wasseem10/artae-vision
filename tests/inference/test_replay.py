import numpy as np
import pytest
from video_intelligence_inference.config import Settings
from video_intelligence_inference.control_plane import resolve_rule_config
from video_intelligence_inference.observer import ObserverDecision
from video_intelligence_inference.replay import run_replay
from video_intelligence_inference.source import EndOfStream, VideoFrame


def semantic_rule():
    return resolve_rule_config(
        {
            "id": "evaluation-1",
            "key": "replay-evaluation",
            "rule_type": "semantic_vision",
            "object_class": "visual_event",
            "duration_seconds": 0,
            "minimum_confidence": 0.7,
            "absence_grace_seconds": 1,
            "zone": {
                "id": "zone-1",
                "name": "Full frame",
                "geometry_type": "polygon",
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 1, "y": 0},
                    {"x": 1, "y": 1},
                ],
            },
            "spec": {
                "schema_version": 3,
                "rule_type": "semantic_vision",
                "instruction": "Alert when a screen turns off.",
                "object_class": "visual_event",
                "zone_id": "zone-1",
                "zone_name": "Full frame",
                "minimum_confidence": 0.7,
                "absence_grace_seconds": 1,
                "confirmation_windows": 1,
                "cooldown_seconds": 0,
            },
            "execution_plan": {
                "schema_version": 1,
                "strategy": "semantic_window",
                "provider_requests": True,
            },
        }
    )


class FakeSource:
    fps = 1.0

    def __init__(self) -> None:
        self._index = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> VideoFrame:
        if self._index >= 10:
            raise EndOfStream("complete")
        index = self._index
        self._index += 1
        return VideoFrame(
            image=np.zeros((16, 16, 3), dtype=np.uint8),
            timestamp_seconds=float(index),
            sequence=index,
        )


class FakeProvider:
    name = "fake-vision"

    def analyze(self, window, rule: str) -> ObserverDecision:
        assert rule == "Alert when a screen turns off."
        return ObserverDecision(
            triggered=True,
            confidence=0.9,
            summary="Screen is off.",
            first_frame=2,
            input_tokens=100,
            output_tokens=10,
        )

    def close(self) -> None:
        return None


def test_semantic_replay_processes_every_window_and_counts_usage() -> None:
    progress: list[float] = []
    output = run_replay(
        Settings(
            observer_sample_fps=1,
            observer_window_frames=4,
            observer_overlap_frames=2,
            observer_frame_width=96,
            observer_frame_height=54,
            observer_sheet_columns=2,
            observer_max_requests_per_minute=100,
            observer_max_requests_per_day=100,
        ),
        source_uri="fixture.mp4",
        duration_seconds=10,
        rule=semantic_rule(),
        source_factory=lambda *_args, **_kwargs: FakeSource(),
        provider_factory=lambda _settings: FakeProvider(),
        on_progress=progress.append,
    )

    assert output.provider_requests == 4
    assert output.input_tokens == 400
    assert output.output_tokens == 40
    assert [interval.start_seconds for interval in output.intervals] == [1, 3, 5, 7]
    assert [interval.end_seconds for interval in output.intervals] == [3, 5, 7, 9]
    assert progress == list(map(float, range(10)))


@pytest.mark.parametrize("source_uri", ["webcam:0", "rtsp://camera/live"])
def test_replay_rejects_unbounded_live_sources(source_uri: str) -> None:
    with pytest.raises(ValueError, match="finite video file"):
        run_replay(
            Settings(),
            source_uri=source_uri,
            duration_seconds=10,
            rule=semantic_rule(),
        )
