import pytest
from video_intelligence_inference.detector import Detection
from video_intelligence_inference.rules import (
    CountThresholdRule,
    CountThresholdRuleEngine,
    DwellRule,
    DwellRuleEngine,
    DwellRuleSetEngine,
    LineCrossingRule,
    LineCrossingRuleEngine,
    RuleSetEngine,
    ZoneTransitionRule,
    ZoneTransitionRuleEngine,
)
from video_intelligence_inference.zones import Line, Point, Zone


def person(track_id: int, *, inside: bool = True) -> Detection:
    if inside:
        return Detection(40, 20, 60, 80, "person", 0.9, track_id=track_id)
    return Detection(0, 0, 10, 10, "person", 0.9, track_id=track_id)


def make_engine(duration: float = 5, grace: float = 1) -> DwellRuleEngine:
    zone = Zone.parse("loading-zone", "0.2,0.2;0.8,0.2;0.8,0.9;0.2,0.9")
    return DwellRuleEngine(
        DwellRule(
            id="person-dwell",
            object_class="person",
            zone=zone,
            duration_seconds=duration,
            absence_grace_seconds=grace,
        )
    )


def evaluate(engine: DwellRuleEngine, detections: list[Detection], at: float):
    return engine.evaluate(
        detections,
        timestamp_seconds=at,
        frame_width=100,
        frame_height=100,
    )


def test_dwell_rule_fires_once_per_continuous_visit() -> None:
    engine = make_engine()

    assert evaluate(engine, [person(7)], 0) == []
    assert evaluate(engine, [person(7)], 4.9) == []
    matches = evaluate(engine, [person(7)], 5)
    assert len(matches) == 1
    assert matches[0].track_id == 7
    assert matches[0].dwell_seconds == 5
    assert evaluate(engine, [person(7)], 8) == []

    assert evaluate(engine, [person(7, inside=False)], 9) == []
    assert evaluate(engine, [person(7)], 10) == []
    assert len(evaluate(engine, [person(7)], 15)) == 1


def test_short_tracking_gap_does_not_reset_dwell_timer() -> None:
    engine = make_engine(duration=2, grace=1)

    evaluate(engine, [person(3)], 0)
    evaluate(engine, [], 0.5)
    matches = evaluate(engine, [person(3)], 2)

    assert len(matches) == 1
    assert matches[0].entered_at_seconds == 0


def test_long_tracking_gap_resets_dwell_timer() -> None:
    engine = make_engine(duration=2, grace=1)

    evaluate(engine, [person(3)], 0)
    evaluate(engine, [], 1.1)

    assert evaluate(engine, [person(3)], 2) == []
    assert len(evaluate(engine, [person(3)], 4)) == 1


def test_rule_set_evaluates_multiple_jobs_from_the_same_detections() -> None:
    zone = Zone.parse("loading-zone", "0.2,0.2;0.8,0.2;0.8,0.9;0.2,0.9")
    engine = DwellRuleSetEngine(
        [
            DwellRule("quick-job", "person", zone, 1, 0.25, 1),
            DwellRule("long-job", "person", zone, 2, 0.25, 1),
        ]
    )

    assert evaluate(engine, [person(7)], 0) == []
    assert [match.rule_id for match in evaluate(engine, [person(7)], 1)] == [
        "quick-job"
    ]
    assert [match.rule_id for match in evaluate(engine, [person(7)], 2)] == ["long-job"]


def test_rule_set_rejects_duplicate_job_ids() -> None:
    zone = Zone.parse("loading-zone", "0.2,0.2;0.8,0.2;0.8,0.9;0.2,0.9")
    rule = DwellRule("duplicate", "person", zone, 1)

    with pytest.raises(ValueError, match="unique"):
        DwellRuleSetEngine([rule, rule])


def test_entry_and_exit_jobs_follow_persistent_track_transitions() -> None:
    zone = Zone.parse("door", "0.2,0.2;0.8,0.2;0.8,0.9;0.2,0.9")
    entry = ZoneTransitionRuleEngine(
        ZoneTransitionRule("entry", "zone_entry", "person", zone)
    )
    exit_job = ZoneTransitionRuleEngine(
        ZoneTransitionRule("exit", "zone_exit", "person", zone)
    )

    assert evaluate(entry, [person(4, inside=False)], 0) == []
    assert evaluate(exit_job, [person(4, inside=False)], 0) == []
    assert evaluate(entry, [person(4)], 1)[0].event_type == "zone_entry"
    assert evaluate(exit_job, [person(4)], 1) == []
    assert evaluate(entry, [person(4, inside=False)], 2) == []
    assert evaluate(exit_job, [person(4, inside=False)], 2)[0].event_type == "zone_exit"


def test_count_threshold_confirms_and_rearms() -> None:
    zone = Zone.parse("queue", "0.2,0.2;0.8,0.2;0.8,0.9;0.2,0.9")
    engine = CountThresholdRuleEngine(
        CountThresholdRule("queue-high", "person", zone, "at_least", 2, 1)
    )

    assert evaluate(engine, [person(1), person(2)], 0) == []
    match = evaluate(engine, [person(1), person(2)], 1)[0]
    assert match.event_type == "count_threshold"
    assert match.track_id is None
    assert match.details["count"] == 2
    assert evaluate(engine, [person(1), person(2)], 2) == []
    assert evaluate(engine, [person(1)], 3) == []
    assert evaluate(engine, [person(1), person(2)], 4) == []
    assert len(evaluate(engine, [person(1), person(2)], 5)) == 1


def test_line_crossing_respects_segment_and_direction() -> None:
    line = Line("gate", Point(0.5, 0.2), Point(0.5, 0.8))
    engine = LineCrossingRuleEngine(
        LineCrossingRule("gate-cross", "person", line, "reverse")
    )
    left = Detection(20, 20, 30, 50, "person", 0.9, track_id=8)
    right = Detection(70, 20, 80, 50, "person", 0.9, track_id=8)

    assert evaluate(engine, [left], 0) == []
    match = evaluate(engine, [right], 1)[0]
    assert match.event_type == "line_crossing"
    assert match.details["direction"] == "reverse"

    outside_segment = LineCrossingRuleEngine(
        LineCrossingRule(
            "short-line", "person", Line("short", Point(0.5, 0.1), Point(0.5, 0.2))
        )
    )
    assert evaluate(outside_segment, [left], 0) == []
    assert evaluate(outside_segment, [right], 1) == []


def test_heterogeneous_rule_set_shares_one_detection_list() -> None:
    zone = Zone.parse("door", "0.2,0.2;0.8,0.2;0.8,0.9;0.2,0.9")
    engines = RuleSetEngine(
        [
            DwellRuleEngine(
                DwellRule("presence", "person", zone, 0, event_type="zone_presence")
            ),
            ZoneTransitionRuleEngine(
                ZoneTransitionRule("entry", "zone_entry", "person", zone)
            ),
        ]
    )

    matches = evaluate(engines, [person(7)], 0)
    assert {match.event_type for match in matches} == {"zone_presence", "zone_entry"}
