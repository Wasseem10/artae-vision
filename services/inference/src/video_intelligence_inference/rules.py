"""Deterministic temporal rules evaluated from persistent object tracks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from video_intelligence_inference.detector import Detection
from video_intelligence_inference.zones import Line, Point, Zone, detection_anchor


@dataclass(frozen=True, slots=True)
class DwellRule:
    id: str
    object_class: str
    zone: Zone
    duration_seconds: float
    minimum_confidence: float = 0.25
    absence_grace_seconds: float = 1.0
    event_type: Literal["object_dwell", "zone_dwell", "zone_presence"] = "object_dwell"

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Rule id cannot be empty.")
        if self.duration_seconds < 0 or (
            self.duration_seconds == 0 and self.event_type != "zone_presence"
        ):
            raise ValueError("Dwell duration must be positive unless this is presence.")
        if not 0 <= self.minimum_confidence <= 1:
            raise ValueError("Minimum confidence must be between zero and one.")
        if self.absence_grace_seconds < 0:
            raise ValueError("Absence grace period cannot be negative.")


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule_id: str
    track_id: int | None
    object_class: str
    zone_name: str
    entered_at_seconds: float
    occurred_at_seconds: float
    dwell_seconds: float
    confidence: float
    event_type: str = "object_dwell"
    details: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class _DwellState:
    entered_at_seconds: float
    last_seen_seconds: float
    fired: bool = False


class DwellRuleEngine:
    """Track how long each object ID remains inside one configured zone."""

    def __init__(self, rule: DwellRule) -> None:
        self.rule = rule
        self._states: dict[int, _DwellState] = {}
        # Presence is a property of the zone, not of a detector-assigned track ID.
        # Keeping one scene-level state prevents a brief tracker ID change from
        # announcing the same continuously present object as a new event.
        self._presence_state: _DwellState | None = None

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        if timestamp_seconds < 0:
            raise ValueError("Frame timestamp cannot be negative.")

        if self.rule.event_type == "zone_presence":
            return self._evaluate_presence(
                detections,
                timestamp_seconds=timestamp_seconds,
                frame_width=frame_width,
                frame_height=frame_height,
            )

        seen_inside: set[int] = set()
        matches: list[RuleMatch] = []
        for detection in detections:
            if (
                detection.track_id is None
                or detection.label != self.rule.object_class
                or detection.confidence < self.rule.minimum_confidence
            ):
                continue

            track_id = detection.track_id
            if not self.rule.zone.contains_detection(
                detection,
                frame_width=frame_width,
                frame_height=frame_height,
            ):
                self._states.pop(track_id, None)
                continue

            seen_inside.add(track_id)
            state = self._states.get(track_id)
            if state is None:
                state = _DwellState(timestamp_seconds, timestamp_seconds)
                self._states[track_id] = state
            else:
                state.last_seen_seconds = timestamp_seconds

            dwell_seconds = timestamp_seconds - state.entered_at_seconds
            if not state.fired and dwell_seconds >= self.rule.duration_seconds:
                state.fired = True
                matches.append(
                    RuleMatch(
                        rule_id=self.rule.id,
                        track_id=track_id,
                        object_class=detection.label,
                        zone_name=self.rule.zone.name,
                        entered_at_seconds=state.entered_at_seconds,
                        occurred_at_seconds=timestamp_seconds,
                        dwell_seconds=dwell_seconds,
                        confidence=detection.confidence,
                        event_type=self.rule.event_type,
                    )
                )

        for track_id, state in list(self._states.items()):
            if (
                track_id not in seen_inside
                and timestamp_seconds - state.last_seen_seconds > self.rule.absence_grace_seconds
            ):
                del self._states[track_id]

        return matches

    def _evaluate_presence(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        candidates = [
            detection
            for detection in detections
            if detection.track_id is not None
            and detection.label == self.rule.object_class
            and detection.confidence >= self.rule.minimum_confidence
            and self.rule.zone.contains_detection(
                detection,
                frame_width=frame_width,
                frame_height=frame_height,
            )
        ]
        if not candidates:
            state = self._presence_state
            if (
                state is not None
                and timestamp_seconds - state.last_seen_seconds > self.rule.absence_grace_seconds
            ):
                self._presence_state = None
            return []

        strongest = max(candidates, key=lambda detection: detection.confidence)
        state = self._presence_state
        if state is None:
            state = _DwellState(timestamp_seconds, timestamp_seconds)
            self._presence_state = state
        else:
            state.last_seen_seconds = timestamp_seconds

        dwell_seconds = timestamp_seconds - state.entered_at_seconds
        if state.fired or dwell_seconds < self.rule.duration_seconds:
            return []
        state.fired = True
        return [
            RuleMatch(
                rule_id=self.rule.id,
                track_id=strongest.track_id,
                object_class=strongest.label,
                zone_name=self.rule.zone.name,
                entered_at_seconds=state.entered_at_seconds,
                occurred_at_seconds=timestamp_seconds,
                dwell_seconds=dwell_seconds,
                confidence=strongest.confidence,
                event_type=self.rule.event_type,
            )
        ]

    def active_dwells(self, timestamp_seconds: float) -> dict[int, float]:
        return {
            track_id: max(0.0, timestamp_seconds - state.entered_at_seconds)
            for track_id, state in self._states.items()
        }


class DwellRuleSetEngine:
    """Evaluate several independent dwell jobs against one shared detection result."""

    def __init__(self, rules: list[DwellRule] | tuple[DwellRule, ...]) -> None:
        if not rules:
            raise ValueError("At least one dwell rule is required.")
        rule_ids = [rule.id for rule in rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("Dwell rule IDs must be unique within a camera assignment.")
        self.rules = tuple(rules)
        self._engines = tuple(DwellRuleEngine(rule) for rule in self.rules)

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        matches: list[RuleMatch] = []
        for engine in self._engines:
            matches.extend(
                engine.evaluate(
                    detections,
                    timestamp_seconds=timestamp_seconds,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            )
        return matches


class RuleEngine(Protocol):
    rule: object

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]: ...


@dataclass(frozen=True, slots=True)
class ZoneTransitionRule:
    id: str
    event_type: Literal["zone_entry", "zone_exit"]
    object_class: str
    zone: Zone
    minimum_confidence: float = 0.25
    absence_grace_seconds: float = 1.0


@dataclass(slots=True)
class _TransitionState:
    inside: bool
    last_seen_seconds: float


class ZoneTransitionRuleEngine:
    """Detect tracked-object entry or exit transitions for one polygon."""

    def __init__(self, rule: ZoneTransitionRule) -> None:
        self.rule = rule
        self._states: dict[int, _TransitionState] = {}

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        seen: set[int] = set()
        matches: list[RuleMatch] = []
        for detection in detections:
            if (
                detection.track_id is None
                or detection.label != self.rule.object_class
                or detection.confidence < self.rule.minimum_confidence
            ):
                continue
            track_id = detection.track_id
            seen.add(track_id)
            inside = self.rule.zone.contains_detection(
                detection, frame_width=frame_width, frame_height=frame_height
            )
            previous = self._states.get(track_id)
            should_fire = (
                self.rule.event_type == "zone_entry"
                and inside
                and (previous is None or not previous.inside)
            ) or (
                self.rule.event_type == "zone_exit"
                and not inside
                and previous is not None
                and previous.inside
            )
            self._states[track_id] = _TransitionState(inside, timestamp_seconds)
            if should_fire:
                matches.append(
                    RuleMatch(
                        rule_id=self.rule.id,
                        track_id=track_id,
                        object_class=detection.label,
                        zone_name=self.rule.zone.name,
                        entered_at_seconds=timestamp_seconds,
                        occurred_at_seconds=timestamp_seconds,
                        dwell_seconds=0,
                        confidence=detection.confidence,
                        event_type=self.rule.event_type,
                    )
                )
        for track_id, state in list(self._states.items()):
            if (
                track_id not in seen
                and timestamp_seconds - state.last_seen_seconds > self.rule.absence_grace_seconds
            ):
                del self._states[track_id]
        return matches


@dataclass(frozen=True, slots=True)
class CountThresholdRule:
    id: str
    object_class: str
    zone: Zone
    comparison: Literal["at_least", "at_most"]
    threshold: int
    confirmation_seconds: float = 0.0
    minimum_confidence: float = 0.25

    def __post_init__(self) -> None:
        if self.threshold < 0:
            raise ValueError("Count threshold cannot be negative.")
        if self.confirmation_seconds < 0:
            raise ValueError("Count confirmation cannot be negative.")


class CountThresholdRuleEngine:
    """Fire once when an aggregate in-zone count satisfies a threshold."""

    def __init__(self, rule: CountThresholdRule) -> None:
        self.rule = rule
        self._condition_started: float | None = None
        self._fired = False

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        eligible = [
            detection
            for detection in detections
            if detection.track_id is not None
            and detection.label == self.rule.object_class
            and detection.confidence >= self.rule.minimum_confidence
            and self.rule.zone.contains_detection(
                detection, frame_width=frame_width, frame_height=frame_height
            )
        ]
        count = len({detection.track_id for detection in eligible})
        satisfied = (
            count >= self.rule.threshold
            if self.rule.comparison == "at_least"
            else count <= self.rule.threshold
        )
        if not satisfied:
            self._condition_started = None
            self._fired = False
            return []
        if self._condition_started is None:
            self._condition_started = timestamp_seconds
        elapsed = timestamp_seconds - self._condition_started
        if self._fired or elapsed < self.rule.confirmation_seconds:
            return []
        self._fired = True
        confidence = sum(item.confidence for item in eligible) / len(eligible) if eligible else 1.0
        return [
            RuleMatch(
                rule_id=self.rule.id,
                track_id=None,
                object_class=self.rule.object_class,
                zone_name=self.rule.zone.name,
                entered_at_seconds=self._condition_started,
                occurred_at_seconds=timestamp_seconds,
                dwell_seconds=elapsed,
                confidence=confidence,
                event_type="count_threshold",
                details={
                    "count": count,
                    "comparison": self.rule.comparison,
                    "threshold": self.rule.threshold,
                },
            )
        ]


@dataclass(frozen=True, slots=True)
class LineCrossingRule:
    id: str
    object_class: str
    line: Line
    direction: Literal["any", "forward", "reverse"] = "any"
    minimum_confidence: float = 0.25
    absence_grace_seconds: float = 1.0


@dataclass(slots=True)
class _LineState:
    side: float
    anchor: Point
    last_seen_seconds: float


class LineCrossingRuleEngine:
    """Detect a tracked anchor moving across a directed two-point line."""

    def __init__(self, rule: LineCrossingRule, *, side_epsilon: float = 0.002) -> None:
        self.rule = rule
        self._side_epsilon = side_epsilon
        self._states: dict[int, _LineState] = {}

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        seen: set[int] = set()
        matches: list[RuleMatch] = []
        for detection in detections:
            if (
                detection.track_id is None
                or detection.label != self.rule.object_class
                or detection.confidence < self.rule.minimum_confidence
            ):
                continue
            track_id = detection.track_id
            seen.add(track_id)
            anchor = detection_anchor(detection, frame_width, frame_height)
            side = self.rule.line.side(anchor)
            previous = self._states.get(track_id)
            if abs(side) <= self._side_epsilon:
                if previous is not None:
                    previous.last_seen_seconds = timestamp_seconds
                continue
            direction: str | None = None
            if (
                previous is not None
                and previous.side * side < 0
                and _segments_intersect(
                    previous.anchor,
                    anchor,
                    self.rule.line.start,
                    self.rule.line.end,
                )
            ):
                direction = "forward" if previous.side < side else "reverse"
            self._states[track_id] = _LineState(side, anchor, timestamp_seconds)
            if direction and self.rule.direction in {"any", direction}:
                matches.append(
                    RuleMatch(
                        rule_id=self.rule.id,
                        track_id=track_id,
                        object_class=detection.label,
                        zone_name=self.rule.line.name,
                        entered_at_seconds=timestamp_seconds,
                        occurred_at_seconds=timestamp_seconds,
                        dwell_seconds=0,
                        confidence=detection.confidence,
                        event_type="line_crossing",
                        details={"direction": direction},
                    )
                )
        for track_id, state in list(self._states.items()):
            if (
                track_id not in seen
                and timestamp_seconds - state.last_seen_seconds > self.rule.absence_grace_seconds
            ):
                del self._states[track_id]
        return matches


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orientation(start: Point, end: Point, point: Point) -> float:
        return (end.x - start.x) * (point.y - start.y) - (end.y - start.y) * (point.x - start.x)

    return (
        orientation(a, b, c) * orientation(a, b, d) <= 0
        and orientation(c, d, a) * orientation(c, d, b) <= 0
    )


class RuleSetEngine:
    """Evaluate heterogeneous jobs against one shared detector/tracker pass."""

    def __init__(self, engines: list[RuleEngine] | tuple[RuleEngine, ...]) -> None:
        if not engines:
            raise ValueError("At least one rule engine is required.")
        ids = [engine.rule.id for engine in engines]  # type: ignore[attr-defined]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule IDs must be unique within a camera assignment.")
        self.engines = tuple(engines)

    def evaluate(
        self,
        detections: list[Detection],
        *,
        timestamp_seconds: float,
        frame_width: int,
        frame_height: int,
    ) -> list[RuleMatch]:
        return [
            match
            for engine in self.engines
            for match in engine.evaluate(
                detections,
                timestamp_seconds=timestamp_seconds,
                frame_width=frame_width,
                frame_height=frame_height,
            )
        ]
