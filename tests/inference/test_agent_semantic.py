import queue

import numpy as np
from video_intelligence_inference.agent import (
    _semantic_match,
    _SemanticDecisionGate,
    _SemanticTrigger,
)
from video_intelligence_inference.control_plane import ResolvedRuleConfig
from video_intelligence_inference.observer import ObservationWindow, ObserverDecision
from video_intelligence_inference.zones import Point, Zone


def semantic_rule() -> ResolvedRuleConfig:
    return ResolvedRuleConfig(
        rule_id="hard-hat-rule",
        rule_type="semantic_vision",
        object_class="visual_event",
        minimum_confidence=0.7,
        absence_grace_seconds=1,
        geometry=Zone(
            "Full frame (automatic)",
            (Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)),
        ),
        instruction="Alert me when a person is not wearing a hard hat.",
        confirmation_windows=2,
        cooldown_seconds=60,
    )


def window(sequence: int, ended_at: float) -> ObservationWindow:
    return ObservationWindow(
        sequence=sequence,
        started_at=ended_at - 9,
        ended_at=ended_at,
        sheet=np.zeros((20, 40, 3), dtype=np.uint8),
    )


def test_semantic_gate_confirms_and_deduplicates_positive_windows() -> None:
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    gate = _SemanticDecisionGate(semantic_rule(), outbox)
    positive = ObserverDecision(
        triggered=True,
        confidence=0.92,
        summary="A worker is visible without a hard hat.",
        first_frame=4,
    )

    gate(window(1, 10), positive)
    assert outbox.empty()

    gate(window(2, 15), positive)
    trigger = outbox.get_nowait()
    match = _semantic_match(trigger)
    assert match.event_type == "semantic_vision"
    assert match.rule_id == "hard-hat-rule"
    assert match.confidence == 0.92
    assert match.details["first_frame"] == 4

    gate(window(3, 20), positive)
    gate(window(4, 25), positive)
    assert outbox.empty()


def test_semantic_gate_rejects_low_confidence_decision() -> None:
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    gate = _SemanticDecisionGate(semantic_rule(), outbox)

    gate(
        window(1, 10),
        ObserverDecision(
            triggered=True,
            confidence=0.6,
            summary="Uncertain headwear.",
            first_frame=1,
        ),
    )

    assert outbox.empty()
