from dataclasses import replace

import numpy as np
import pytest
from video_intelligence_inference.config import Settings
from video_intelligence_inference.control_plane import resolve_rule_config
from video_intelligence_inference.detector import (
    Detection,
    PoseKeypoint,
    PoseObservation,
)
from video_intelligence_inference.observer import ObserverDecision, RequestBudget
from video_intelligence_inference.replay import run_replay
from video_intelligence_inference.source import EndOfStream, VideoFrame
from video_intelligence_inference.zones import Point, Zone


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


class TransitionProvider:
    name = "fake-transition-vision"

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, window, rule: str) -> ObserverDecision:
        self.calls += 1
        triggered = self.calls > 1
        return ObserverDecision(
            triggered=triggered,
            confidence=0.9,
            summary="Screen changed state."
            if triggered
            else "Screen baseline is visible.",
            first_frame=2 if triggered else None,
        )

    def close(self) -> None:
        return None


class InWindowTransitionProvider:
    name = "fake-in-window-transition-vision"

    def analyze(self, window, rule: str) -> ObserverDecision:
        return ObserverDecision(
            triggered=True,
            confidence=0.9,
            summary="Baseline and transition are both visible.",
            first_frame=3,
        )

    def close(self) -> None:
        return None


def replay_pose(posture: str) -> PoseObservation:
    points = [PoseKeypoint(0, 0, 0) for _ in range(17)]
    if posture == "upright":
        box = (6, 1, 10, 15)
        core = {
            5: (7, 4), 6: (9, 4), 11: (7, 8), 12: (9, 8),
            13: (7, 11), 14: (9, 11), 15: (7, 14), 16: (9, 14),
        }
    else:
        box = (1, 10, 15, 15)
        core = {
            5: (4, 12), 6: (4, 13), 11: (12, 12), 12: (12, 13),
            13: (13, 12), 14: (13, 13), 15: (14, 12), 16: (14, 13),
        }
    for index, (x, y) in core.items():
        points[index] = PoseKeypoint(x, y, 0.95)
    return PoseObservation(
        Detection(*box, label="person", confidence=0.95, track_id=4),
        tuple(points),
    )


class FakePoseDetector:
    def __init__(self) -> None:
        self.calls = 0

    def track(self, _frame) -> list[PoseObservation]:
        self.calls += 1
        return [replay_pose("upright" if self.calls == 1 else "down")]


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


def test_transition_replay_requires_baseline_and_rearms_after_emission() -> None:
    rule = semantic_rule()
    transition_rule = replace(rule, temporal_mode="transition", baseline_windows=1)
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
        rule=transition_rule,
        source_factory=lambda *_args, **_kwargs: FakeSource(),
        provider_factory=lambda _settings: TransitionProvider(),
    )

    assert output.provider_requests == 4
    assert len(output.intervals) == 1


def test_transition_replay_accepts_baseline_earlier_in_same_window() -> None:
    transition_rule = replace(
        semantic_rule(), temporal_mode="transition", baseline_windows=1
    )
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
        rule=transition_rule,
        source_factory=lambda *_args, **_kwargs: FakeSource(),
        provider_factory=lambda _settings: InWindowTransitionProvider(),
    )

    assert output.provider_requests == 4
    assert len(output.intervals) == 1


def test_semantic_replay_fails_instead_of_silently_skipping_budgeted_windows() -> None:
    with pytest.raises(RuntimeError, match="provider budget exhausted"):
        run_replay(
            Settings(
                observer_sample_fps=1,
                observer_window_frames=4,
                observer_overlap_frames=2,
                observer_frame_width=96,
                observer_frame_height=54,
                observer_sheet_columns=2,
            ),
            source_uri="fixture.mp4",
            duration_seconds=10,
            rule=semantic_rule(),
            source_factory=lambda *_args, **_kwargs: FakeSource(),
            provider_factory=lambda _settings: FakeProvider(),
            request_budget=RequestBudget(per_minute=1, per_day=10),
        )


def test_specialized_pose_replay_runs_without_provider_requests() -> None:
    rule = replace(
        semantic_rule(),
        instruction="Alert me if a person falls to the ground.",
        minimum_confidence=0.5,
        execution_strategy="specialized_pose",
        geometry=Zone(
            "Full frame",
            (Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)),
        ),
    )
    output = run_replay(
        Settings(continuous_recording_archive_enabled=False),
        source_uri="fixture.mp4",
        duration_seconds=10,
        rule=rule,
        source_factory=lambda *_args, **_kwargs: FakeSource(),
        pose_detector_factory=lambda **_kwargs: FakePoseDetector(),
    )

    assert output.provider_requests == 0
    assert len(output.intervals) == 1
    assert output.intervals[0].start_seconds == 1
    assert output.intervals[0].end_seconds == 3


@pytest.mark.parametrize("source_uri", ["webcam:0", "rtsp://camera/live"])
def test_replay_rejects_unbounded_live_sources(source_uri: str) -> None:
    with pytest.raises(ValueError, match="finite video file"):
        run_replay(
            Settings(),
            source_uri=source_uri,
            duration_seconds=10,
            rule=semantic_rule(),
        )
