"""Continuous local pose analysis for visually confirmed person falls.

The detector intentionally requires a temporal sequence: an upright tracked
person, rapid downward motion, and a sustained ground-level posture. A person
who is already lying down does not create an event.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from video_intelligence_inference.detector import Detection, PoseKeypoint, PoseObservation
from video_intelligence_inference.rules import RuleMatch
from video_intelligence_inference.zones import Zone

_FALL_PROMPT = re.compile(
    r"\b(?:fall|falls|fell|fallen|falling|collapse|collapses|collapsed|collapsing)\b",
    re.IGNORECASE,
)


def is_person_fall_instruction(instruction: str | None) -> bool:
    return bool(instruction and _FALL_PROMPT.search(instruction))


@dataclass(frozen=True, slots=True)
class PersonFallRule:
    id: str
    zone: Zone
    minimum_confidence: float = 0.5
    detection_confidence: float = 0.25
    keypoint_confidence: float = 0.35
    minimum_descent_speed: float = 0.35
    fallen_confirmation_seconds: float = 0.7
    partial_view_confirmation_seconds: float = 0.45
    candidate_timeout_seconds: float = 3.0
    recovery_seconds: float = 1.0
    absence_grace_seconds: float = 1.0
    cooldown_seconds: float = 30.0


@dataclass(slots=True)
class _TrackState:
    phase: Literal["unarmed", "upright", "descending", "down", "alerted"] = "unarmed"
    last_center_y: float | None = None
    last_seen_seconds: float = 0.0
    candidate_started_seconds: float | None = None
    down_started_seconds: float | None = None
    down_evidence: Literal["horizontal", "partial_view"] | None = None
    recovery_started_seconds: float | None = None
    peak_descent_speed: float = 0.0
    last_event_seconds: float = float("-inf")


@dataclass(frozen=True, slots=True)
class _PoseFeatures:
    center_y: float
    box_bottom_y: float
    verticality: float
    box_aspect_ratio: float
    visible_core_points: int

    @property
    def upright(self) -> bool:
        return self.verticality >= 0.68 and self.box_aspect_ratio <= 1.05

    @property
    def down(self) -> bool:
        return self.verticality <= 0.48 and self.box_aspect_ratio >= 0.9

    @property
    def partial_view_down(self) -> bool:
        """A person rapidly dropped behind the bottom edge of a fixed camera view.

        This is weaker evidence than a horizontal full-body posture, so it is
        only used after the same tracked person was upright and descended fast.
        """
        return (
            self.center_y >= 0.62
            and self.box_bottom_y >= 0.97
            and self.verticality >= 0.62
            and self.box_aspect_ratio <= 1.2
        )


_SHOULDERS = (5, 6)
_HIPS = (11, 12)
_CORE = (*_SHOULDERS, *_HIPS, 13, 14, 15, 16)


def _visible(keypoints: tuple[PoseKeypoint, ...], indices: tuple[int, ...], threshold: float):
    return [
        keypoints[index]
        for index in indices
        if index < len(keypoints) and keypoints[index].confidence >= threshold
    ]


def _center(points: list[PoseKeypoint]) -> tuple[float, float] | None:
    if not points:
        return None
    return (
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )


def pose_features(
    observation: PoseObservation,
    *,
    frame_height: int,
    keypoint_confidence: float,
) -> _PoseFeatures | None:
    """Convert raw landmarks into camera-scale-independent posture features."""
    if frame_height <= 0:
        raise ValueError("Frame height must be positive")
    shoulders = _center(_visible(observation.keypoints, _SHOULDERS, keypoint_confidence))
    hips = _center(_visible(observation.keypoints, _HIPS, keypoint_confidence))
    visible_core = len(_visible(observation.keypoints, _CORE, keypoint_confidence))
    if shoulders is None or hips is None or visible_core < 4:
        return None
    dx = hips[0] - shoulders[0]
    dy = hips[1] - shoulders[1]
    torso_length = math.hypot(dx, dy)
    if torso_length < 1:
        return None
    box = observation.detection
    width = max(1, box.x2 - box.x1)
    height = max(1, box.y2 - box.y1)
    return _PoseFeatures(
        center_y=((shoulders[1] + hips[1]) / 2) / frame_height,
        box_bottom_y=box.y2 / frame_height,
        verticality=abs(dy) / torso_length,
        box_aspect_ratio=width / height,
        visible_core_points=visible_core,
    )


class PersonFallRuleEngine:
    """Detect one fall transition per tracked person and rearm after recovery."""

    def __init__(self, rule: PersonFallRule) -> None:
        self.rule = rule
        self._states: dict[int, _TrackState] = {}

    def evaluate(
        self,
        observations: list[PoseObservation],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        if timestamp_seconds < 0:
            raise ValueError("Frame timestamp cannot be negative")
        seen: set[int] = set()
        matches: list[RuleMatch] = []
        for observation in observations:
            detection = observation.detection
            track_id = detection.track_id
            if (
                track_id is None
                or detection.confidence < self.rule.detection_confidence
                or not self.rule.zone.contains_detection(
                    detection,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            ):
                continue
            features = pose_features(
                observation,
                frame_height=frame_height,
                keypoint_confidence=self.rule.keypoint_confidence,
            )
            if features is None:
                continue
            seen.add(track_id)
            state = self._states.setdefault(track_id, _TrackState())
            elapsed = max(0.0, timestamp_seconds - state.last_seen_seconds)
            descent_speed = (
                0.0
                if state.last_center_y is None or elapsed <= 0
                else (features.center_y - state.last_center_y) / elapsed
            )
            state.last_center_y = features.center_y
            state.last_seen_seconds = timestamp_seconds
            state.peak_descent_speed = max(state.peak_descent_speed, descent_speed)

            if state.phase in {"unarmed", "upright"}:
                if state.phase == "upright" and descent_speed >= self.rule.minimum_descent_speed:
                    # A falling person can remain vertically oriented during
                    # the descent, especially in a cropped webcam view. Motion
                    # must therefore take precedence over the static upright
                    # classification.
                    state.phase = "descending"
                    state.candidate_started_seconds = timestamp_seconds
                    state.peak_descent_speed = descent_speed
                elif features.upright:
                    state.phase = "upright"
                    state.recovery_started_seconds = None
                continue

            if state.phase == "descending":
                candidate_started = (
                    state.candidate_started_seconds
                    if state.candidate_started_seconds is not None
                    else timestamp_seconds
                )
                candidate_age = timestamp_seconds - candidate_started
                if features.down:
                    state.phase = "down"
                    state.down_started_seconds = timestamp_seconds
                    state.down_evidence = "horizontal"
                elif features.partial_view_down:
                    state.phase = "down"
                    state.down_started_seconds = timestamp_seconds
                    state.down_evidence = "partial_view"
                elif candidate_age > self.rule.candidate_timeout_seconds:
                    self._reset_candidate(state, armed=features.upright)
                continue

            if state.phase == "down":
                still_down = (
                    features.down
                    if state.down_evidence == "horizontal"
                    else features.partial_view_down
                )
                if not still_down:
                    candidate_started = (
                        state.candidate_started_seconds
                        if state.candidate_started_seconds is not None
                        else timestamp_seconds
                    )
                    candidate_age = timestamp_seconds - candidate_started
                    if candidate_age > self.rule.candidate_timeout_seconds:
                        self._reset_candidate(state, armed=features.upright)
                    continue
                down_started = (
                    state.down_started_seconds
                    if state.down_started_seconds is not None
                    else timestamp_seconds
                )
                down_for = timestamp_seconds - down_started
                required_confirmation = (
                    self.rule.partial_view_confirmation_seconds
                    if state.down_evidence == "partial_view"
                    else self.rule.fallen_confirmation_seconds
                )
                if down_for < required_confirmation:
                    continue
                if timestamp_seconds - state.last_event_seconds < self.rule.cooldown_seconds:
                    state.phase = "alerted"
                    continue
                confidence = self._event_confidence(observation, features, state)
                if confidence < self.rule.minimum_confidence:
                    continue
                state.phase = "alerted"
                state.last_event_seconds = timestamp_seconds
                partial_view = state.down_evidence == "partial_view"
                matches.append(
                    RuleMatch(
                        rule_id=self.rule.id,
                        track_id=track_id,
                        object_class="person",
                        zone_name=self.rule.zone.name,
                        entered_at_seconds=(
                            state.candidate_started_seconds
                            if state.candidate_started_seconds is not None
                            else timestamp_seconds
                        ),
                        occurred_at_seconds=timestamp_seconds,
                        dwell_seconds=max(
                            0.0,
                            timestamp_seconds
                            - (
                                state.candidate_started_seconds
                                if state.candidate_started_seconds is not None
                                else timestamp_seconds
                            ),
                        ),
                        confidence=confidence,
                        event_type="person_fall",
                        details={
                            "visual_skill": "pose_action",
                            "summary": (
                                "Possible fall: a tracked person moved rapidly downward "
                                "and remained low in a partially obstructed view."
                                if partial_view
                                else "A tracked person rapidly descended and remained down."
                            ),
                            "fall_evidence": state.down_evidence,
                            "peak_descent_speed_frame_heights_per_second": round(
                                state.peak_descent_speed, 3
                            ),
                            "torso_verticality": round(features.verticality, 3),
                            "box_aspect_ratio": round(features.box_aspect_ratio, 3),
                            "box_bottom_frame_ratio": round(features.box_bottom_y, 3),
                            "visible_core_keypoints": features.visible_core_points,
                            "decision_source": "local_pose_state_machine",
                        },
                    )
                )
                continue

            if state.phase == "alerted":
                if features.upright:
                    if state.recovery_started_seconds is None:
                        state.recovery_started_seconds = timestamp_seconds
                    elif (
                        timestamp_seconds - state.recovery_started_seconds
                        >= self.rule.recovery_seconds
                    ):
                        self._reset_candidate(state, armed=True)
                else:
                    state.recovery_started_seconds = None

        for track_id, state in list(self._states.items()):
            if (
                track_id not in seen
                and timestamp_seconds - state.last_seen_seconds > self.rule.absence_grace_seconds
            ):
                del self._states[track_id]
        return matches

    @staticmethod
    def _reset_candidate(state: _TrackState, *, armed: bool) -> None:
        state.phase = "upright" if armed else "unarmed"
        state.candidate_started_seconds = None
        state.down_started_seconds = None
        state.down_evidence = None
        state.recovery_started_seconds = None
        state.peak_descent_speed = 0.0

    def _event_confidence(
        self,
        observation: PoseObservation,
        features: _PoseFeatures,
        state: _TrackState,
    ) -> float:
        motion_score = min(1.0, state.peak_descent_speed / self.rule.minimum_descent_speed)
        posture_score = (
            0.25
            if state.down_evidence == "partial_view"
            else min(1.0, (1.0 - features.verticality) / 0.52)
        )
        return max(
            0.0,
            min(
                1.0,
                0.45 * observation.detection.confidence + 0.3 * motion_score + 0.25 * posture_score,
            ),
        )


class PersonFallRuleSetEngine:
    def __init__(self, rules: list[PersonFallRule] | tuple[PersonFallRule, ...]) -> None:
        if not rules:
            raise ValueError("At least one fall rule is required")
        ids = [rule.id for rule in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Fall rule IDs must be unique within a camera assignment")
        self._engines = tuple(PersonFallRuleEngine(rule) for rule in rules)

    def evaluate(
        self,
        observations: list[PoseObservation],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        matches: list[RuleMatch] = []
        for engine in self._engines:
            matches.extend(
                engine.evaluate(
                    observations,
                    timestamp_seconds=timestamp_seconds,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            )
        return matches


def pose_detections(observations: list[PoseObservation]) -> list[Detection]:
    return [observation.detection for observation in observations]
