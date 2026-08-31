import json
import threading
import time
from datetime import date
from pathlib import Path

import httpx
import numpy as np
from video_intelligence_inference.observer import (
    ContinuousObserver,
    DryRunVisionClient,
    GeminiVisionClient,
    ObservationWindow,
    ObserverArtifactSink,
    ObserverDecision,
    OverlappingSheetSampler,
    QwenVisionClient,
    RequestBudget,
)


def test_sampler_emits_overlapping_chronological_sheets() -> None:
    sampler = OverlappingSheetSampler(
        sample_fps=1,
        window_frames=4,
        overlap_frames=2,
        frame_width=20,
        frame_height=10,
        columns=2,
    )
    windows = []
    for second in range(6):
        frame = np.full((12, 24, 3), second * 20, dtype=np.uint8)
        window = sampler.add(frame, float(second))
        if window is not None:
            windows.append(window)

    assert [window.sequence for window in windows] == [1, 2]
    assert [(window.started_at, window.ended_at) for window in windows] == [
        (0.0, 3.0),
        (2.0, 5.0),
    ]
    assert windows[0].sheet.shape == (20, 40, 3)


def test_sampler_flushes_one_partial_window_for_a_short_finite_replay() -> None:
    sampler = OverlappingSheetSampler(
        sample_fps=1,
        window_frames=10,
        overlap_frames=5,
        frame_width=20,
        frame_height=10,
        columns=5,
    )
    for second in range(6):
        assert sampler.add(np.zeros((12, 24, 3), dtype=np.uint8), float(second)) is None

    partial = sampler.flush()

    assert partial is not None
    assert (partial.started_at, partial.ended_at) == (0.0, 5.0)
    assert sampler.flush() is None


def test_sampler_does_not_flush_overlap_after_a_complete_window() -> None:
    sampler = OverlappingSheetSampler(
        sample_fps=1,
        window_frames=4,
        overlap_frames=2,
        frame_width=20,
        frame_height=10,
        columns=2,
    )
    completed = None
    for second in range(4):
        completed = (
            sampler.add(np.zeros((12, 24, 3), dtype=np.uint8), float(second))
            or completed
        )

    assert completed is not None
    assert sampler.flush() is None


def test_sampler_flushes_trailing_frames_after_a_complete_window() -> None:
    sampler = OverlappingSheetSampler(
        sample_fps=1,
        window_frames=4,
        overlap_frames=2,
        frame_width=20,
        frame_height=10,
        columns=2,
    )
    for second in range(5):
        sampler.add(np.zeros((12, 24, 3), dtype=np.uint8), float(second))

    trailing = sampler.flush()

    assert trailing is not None
    assert (trailing.started_at, trailing.ended_at) == (2.0, 4.0)


def test_qwen_client_sends_sheet_and_validates_json() -> None:
    request_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "triggered": True,
                                    "confidence": 0.91,
                                    "summary": "A person fell.",
                                    "first_frame": 7,
                                    "scene_observations": [
                                        {
                                            "stable_key": "floor-area",
                                            "label": "Floor area",
                                            "kind": "region",
                                            "bounding_box": {
                                                "x": 0.1,
                                                "y": 0.5,
                                                "width": 0.8,
                                                "height": 0.4,
                                            },
                                            "description": "Visible floor",
                                            "state": "clear",
                                            "confidence": 0.88,
                                            "attributes": {},
                                            "relationships": [],
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://example.test/v1",
    )
    client = QwenVisionClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="qwen3-vl-flash",
        timeout_seconds=5,
        client=http_client,
    )
    decision = client.analyze(
        ObservationWindow(
            sequence=1,
            started_at=0,
            ended_at=9,
            sheet=np.zeros((20, 40, 3), dtype=np.uint8),
        ),
        "Alert when a person falls.",
    )

    assert decision.triggered is True
    assert decision.first_frame == 7
    assert decision.scene_observations[0].stable_key == "floor-area"
    assert request_payload["model"] == "qwen3-vl-flash"


def test_gemini_client_sends_sheet_and_validates_structured_json() -> None:
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["api_key"] = request.headers.get("x-goog-api-key")
        captured_request["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "triggered": True,
                                            "confidence": 0.94,
                                            "summary": "A masked person entered.",
                                            "first_frame": 3,
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 120,
                },
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta",
        headers={"x-goog-api-key": "test-key"},
    )
    client = GeminiVisionClient(
        api_key="test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model="gemini-3.5-flash-lite",
        timeout_seconds=5,
        client=http_client,
    )

    decision = client.analyze(
        ObservationWindow(
            sequence=1,
            started_at=0,
            ended_at=9,
            sheet=np.zeros((20, 40, 3), dtype=np.uint8),
        ),
        "Alert when a masked person enters.",
    )

    payload = captured_request["payload"]
    assert isinstance(payload, dict)
    assert decision.triggered is True
    assert decision.first_frame == 3
    assert captured_request["api_key"] == "test-key"
    assert captured_request["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-3.5-flash-lite:generateContent"
    )
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "MINIMAL"}
    assert "Compare the same people" in payload["contents"][0]["parts"][0]["text"]
    assert (
        "scene_observations"
        in payload["generationConfig"]["responseJsonSchema"]["required"]
    )


def test_gemini_client_clamps_model_boxes_that_cross_the_frame_edge() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        content = {
            "triggered": True,
            "confidence": 0.9,
            "summary": "A transition is visible.",
            "first_frame": 3,
            "scene_observations": [
                {
                    "stable_key": "person",
                    "label": "Person",
                    "kind": "tracked_entity",
                    "bounding_box": {
                        "x": 0.8,
                        "y": 1.0,
                        "width": 0.4,
                        "height": 0.3,
                    },
                    "description": "Visible person",
                    "state": "observed",
                    "confidence": 0.9,
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(content)}]}}],
                "usageMetadata": {},
            },
        )

    client = GeminiVisionClient(
        api_key="test-key",
        base_url="https://example.test/v1beta",
        model="gemini-test",
        timeout_seconds=5,
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://example.test/v1beta",
        ),
    )
    decision = client.analyze(
        ObservationWindow(1, 0, 3, np.zeros((20, 40, 3), dtype=np.uint8)),
        "Alert when a transition occurs.",
    )

    box = decision.scene_observations[0].bounding_box
    assert box.x + box.width <= 1
    assert box.y + box.height <= 1


def test_dry_run_provider_triggers_predictably() -> None:
    provider = DryRunVisionClient(trigger_every=2)
    window = ObservationWindow(
        sequence=2,
        started_at=0,
        ended_at=9,
        sheet=np.zeros((20, 40, 3), dtype=np.uint8),
    )

    decision = provider.analyze(window, "Alert when anything happens.")

    assert decision.triggered is True
    assert decision.first_frame == 1


def test_request_budget_enforces_minute_and_day_limits() -> None:
    budget = RequestBudget(per_minute=2, per_day=3)
    today = date(2026, 8, 19)

    assert budget.acquire(now_monotonic=0, today=today) == (True, None)
    assert budget.acquire(now_monotonic=1, today=today) == (True, None)
    assert budget.acquire(now_monotonic=2, today=today) == (
        False,
        "per-minute request budget reached",
    )
    assert budget.acquire(now_monotonic=61, today=today) == (True, None)
    assert budget.acquire(now_monotonic=62, today=today) == (
        False,
        "daily request budget reached",
    )


def test_artifact_sink_persists_sheet_and_decision(tmp_path: Path) -> None:
    window = ObservationWindow(
        sequence=4,
        started_at=10,
        ended_at=19,
        sheet=np.zeros((20, 40, 3), dtype=np.uint8),
    )
    decision = DryRunVisionClient(trigger_every=1).analyze(window, "Test rule")
    sink = ObserverArtifactSink(tmp_path, "triggered")

    paths = sink.write(
        provider="dry-run",
        rule="Test rule",
        window=window,
        decision=decision,
    )

    assert paths is not None
    sheet_path, decision_path = paths
    assert sheet_path.exists()
    payload = json.loads(decision_path.read_text(encoding="utf-8"))
    assert payload["decision"]["triggered"] is True
    assert payload["provider"] == "dry-run"


def test_observer_keeps_last_decision_visible_while_next_window_runs() -> None:
    class BlockingSecondProvider:
        name = "blocking-test"

        def __init__(self) -> None:
            self.calls = 0
            self.second_started = threading.Event()
            self.release_second = threading.Event()

        def analyze(self, window: ObservationWindow, rule: str) -> ObserverDecision:
            self.calls += 1
            if self.calls == 2:
                self.second_started.set()
                self.release_second.wait(timeout=2)
            return ObserverDecision(
                triggered=self.calls == 1,
                confidence=0.9,
                summary="First alert" if self.calls == 1 else "Second result",
                first_frame=1 if self.calls == 1 else None,
            )

        def close(self) -> None:
            return None

    provider = BlockingSecondProvider()
    observer = ContinuousObserver(
        provider,
        "Test rule",
        max_requests_per_minute=10,
        max_requests_per_day=10,
    )
    first = ObservationWindow(1, 0, 1, np.zeros((20, 40, 3), dtype=np.uint8))
    second = ObservationWindow(2, 2, 3, np.zeros((20, 40, 3), dtype=np.uint8))

    observer.start()
    try:
        observer.submit(first)
        deadline = time.monotonic() + 2
        while observer.snapshot().decision is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert observer.snapshot().decision is not None

        observer.submit(second)
        assert provider.second_started.wait(timeout=2)
        snapshot = observer.snapshot()
        assert snapshot.state == "analyzing"
        assert snapshot.decision is not None
        assert snapshot.decision.summary == "First alert"
    finally:
        provider.release_second.set()
        observer.close()
