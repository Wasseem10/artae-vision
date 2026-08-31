import queue
from dataclasses import replace

import numpy as np
from video_intelligence_inference.agent import (
    _semantic_match,
    _SemanticDecisionGate,
    _SemanticTrigger,
)
from video_intelligence_inference.control_plane import ResolvedRuleConfig
from video_intelligence_inference.observer import ObservationWindow, ObserverDecision
from video_intelligence_inference.zones import Point, Zone


class StubVerifier:
    def __init__(self, decision: ObserverDecision | None, *, fails: bool = False) -> None:
        self.decision = decision
        self.fails = fails

    @property
    def name(self) -> str:
        return "independent-verifier"

    def analyze(self, window: ObservationWindow, rule: str) -> ObserverDecision:
        del window, rule
        if self.fails:
            raise RuntimeError("provider unavailable")
        assert self.decision is not None
        return self.decision

    def close(self) -> None:
        return None


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


def test_semantic_gate_records_independent_rejection_for_control_plane() -> None:
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    verifier = StubVerifier(
        ObserverDecision(
            triggered=False,
            confidence=0.96,
            summary="The worker's hard hat remains visible.",
        )
    )
    gate = _SemanticDecisionGate(
        semantic_rule(),
        outbox,
        proposer_model="proposer-model",
        verifier=verifier,
    )
    proposal = ObserverDecision(
        triggered=True,
        confidence=0.92,
        summary="A worker appears to be missing a hard hat.",
        first_frame=4,
    )
    gate(window(1, 10), proposal)
    gate(window(2, 15), proposal)

    match = _semantic_match(outbox.get_nowait())
    verification = match.details["independent_verification"]
    assert isinstance(verification, dict)
    assert verification["status"] == "rejected"
    assert verification["triggered"] is False
    assert match.details["proposer_model"] == "proposer-model"


def test_semantic_gate_preserves_verifier_failure_as_uncertain_case() -> None:
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    gate = _SemanticDecisionGate(
        semantic_rule(),
        outbox,
        proposer_model="proposer-model",
        verifier=StubVerifier(None, fails=True),
    )
    proposal = ObserverDecision(
        triggered=True,
        confidence=0.92,
        summary="A worker appears to be missing a hard hat.",
        first_frame=4,
    )
    gate(window(1, 10), proposal)
    gate(window(2, 15), proposal)

    match = _semantic_match(outbox.get_nowait())
    verification = match.details["independent_verification"]
    assert isinstance(verification, dict)
    assert verification["status"] == "uncertain"
    assert verification["error"] == "RuntimeError"


def test_transition_gate_requires_and_rearms_a_visible_baseline() -> None:
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    transition_rule = replace(
        semantic_rule(),
        instruction="Alert when a worker removes their hard hat.",
        confirmation_windows=1,
        cooldown_seconds=0,
        temporal_mode="transition",
        baseline_windows=1,
    )
    gate = _SemanticDecisionGate(transition_rule, outbox)
    positive = ObserverDecision(
        triggered=True,
        confidence=0.92,
        summary="The worker removes the hard hat.",
        first_frame=1,
    )
    negative = ObserverDecision(
        triggered=False,
        confidence=0.95,
        summary="No removal transition is visible.",
        first_frame=None,
    )

    gate(window(1, 10), positive)
    assert outbox.empty()
    gate(window(2, 15), negative)
    gate(window(3, 20), positive)
    assert outbox.get_nowait().rule.temporal_mode == "transition"

    gate(window(4, 25), positive)
    assert outbox.empty()
    gate(window(5, 30), negative)
    gate(window(6, 35), positive)
    assert outbox.get_nowait().window.sequence == 6


def test_transition_gate_accepts_a_baseline_visible_earlier_in_the_same_window() -> (
    None
):
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    transition_rule = replace(
        semantic_rule(),
        confirmation_windows=1,
        cooldown_seconds=0,
        temporal_mode="transition",
        baseline_windows=1,
    )
    gate = _SemanticDecisionGate(transition_rule, outbox)

    gate(
        window(1, 10),
        ObserverDecision(
            triggered=True,
            confidence=0.95,
            summary="The transition starts after the initial baseline frames.",
            first_frame=4,
        ),
    )

    assert outbox.get_nowait().window.sequence == 1


def test_transition_gate_does_not_treat_uncertainty_as_a_baseline() -> None:
    outbox: queue.SimpleQueue[_SemanticTrigger] = queue.SimpleQueue()
    transition_rule = replace(
        semantic_rule(),
        confirmation_windows=1,
        cooldown_seconds=0,
        temporal_mode="transition",
        baseline_windows=1,
    )
    gate = _SemanticDecisionGate(transition_rule, outbox)
    gate(
        window(1, 10),
        ObserverDecision(
            triggered=False,
            confidence=0.3,
            summary="The scene is too occluded to establish a baseline.",
        ),
    )
    gate(
        window(2, 15),
        ObserverDecision(
            triggered=True,
            confidence=0.95,
            summary="A transition is visible.",
        ),
    )

    assert outbox.empty()
