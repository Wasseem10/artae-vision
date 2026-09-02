from video_intelligence_inference.detector import (
    Detection,
    PoseKeypoint,
    PoseObservation,
)
from video_intelligence_inference.pose_action import (
    PersonFallRule,
    PersonFallRuleEngine,
    is_person_fall_instruction,
)
from video_intelligence_inference.zones import Point, Zone

FULL_FRAME = Zone(
    "Full frame",
    (Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)),
)


def pose(
    track_id: int,
    *,
    posture: str,
    confidence: float = 0.95,
) -> PoseObservation:
    points = [PoseKeypoint(0, 0, 0) for _ in range(17)]
    if posture == "upright":
        box = (420, 150, 580, 900)
        coordinates = {
            5: (470, 300),
            6: (530, 300),
            11: (480, 560),
            12: (520, 560),
            13: (480, 700),
            14: (520, 700),
            15: (480, 860),
            16: (520, 860),
        }
    elif posture == "sitting":
        box = (380, 300, 620, 760)
        coordinates = {
            5: (470, 390),
            6: (530, 390),
            11: (475, 570),
            12: (525, 570),
            13: (430, 650),
            14: (570, 650),
            15: (420, 730),
            16: (580, 730),
        }
    else:
        box = (220, 650, 820, 930)
        coordinates = {
            5: (330, 760),
            6: (350, 800),
            11: (590, 770),
            12: (610, 810),
            13: (680, 780),
            14: (690, 820),
            15: (760, 790),
            16: (770, 830),
        }
    for index, (x, y) in coordinates.items():
        points[index] = PoseKeypoint(x, y, 0.95)
    return PoseObservation(
        detection=Detection(
            x1=box[0],
            y1=box[1],
            x2=box[2],
            y2=box[3],
            label="person",
            confidence=confidence,
            track_id=track_id,
        ),
        keypoints=tuple(points),
    )


def evaluate(engine: PersonFallRuleEngine, value: PoseObservation, at: float):
    return engine.evaluate(
        [value],
        timestamp_seconds=at,
        frame_width=1000,
        frame_height=1000,
    )


def test_fall_prompt_router_is_narrow() -> None:
    assert is_person_fall_instruction("Alert me if a worker falls") is True
    assert is_person_fall_instruction("Alert me if someone collapses") is True
    assert is_person_fall_instruction("Tell me if someone is lying down") is False
    assert is_person_fall_instruction("Tell me if someone jumps") is False


def test_fast_descent_then_sustained_down_posture_emits_one_fall() -> None:
    engine = PersonFallRuleEngine(
        PersonFallRule(
            id="fall-1",
            zone=FULL_FRAME,
            fallen_confirmation_seconds=0.5,
            cooldown_seconds=10,
        )
    )

    assert evaluate(engine, pose(7, posture="upright"), 0.0) == []
    assert evaluate(engine, pose(7, posture="down"), 0.25) == []
    assert evaluate(engine, pose(7, posture="down"), 0.5) == []
    matches = evaluate(engine, pose(7, posture="down"), 1.0)
    assert len(matches) == 1
    assert matches[0].event_type == "person_fall"
    assert matches[0].track_id == 7
    assert matches[0].entered_at_seconds == 0.25
    assert matches[0].details["decision_source"] == "local_pose_state_machine"
    assert evaluate(engine, pose(7, posture="down"), 2.0) == []


def test_sitting_and_starting_down_do_not_trigger() -> None:
    engine = PersonFallRuleEngine(PersonFallRule(id="fall-1", zone=FULL_FRAME))

    assert evaluate(engine, pose(1, posture="upright"), 0.0) == []
    assert evaluate(engine, pose(1, posture="sitting"), 0.25) == []
    assert evaluate(engine, pose(1, posture="sitting"), 1.5) == []
    assert evaluate(engine, pose(2, posture="down"), 0.0) == []
    assert evaluate(engine, pose(2, posture="down"), 2.0) == []


def test_recovery_rearms_track_for_a_later_fall() -> None:
    engine = PersonFallRuleEngine(
        PersonFallRule(
            id="fall-1",
            zone=FULL_FRAME,
            fallen_confirmation_seconds=0.25,
            recovery_seconds=0.5,
            cooldown_seconds=0,
        )
    )
    sequence = [
        ("upright", 0.0),
        ("down", 0.25),
        ("down", 0.5),
        ("down", 0.75),
        ("upright", 1.0),
        ("upright", 1.6),
        ("down", 1.85),
        ("down", 2.1),
        ("down", 2.4),
    ]
    matches = [
        match
        for posture, timestamp in sequence
        for match in evaluate(engine, pose(3, posture=posture), timestamp)
    ]
    assert len(matches) == 2


def test_tracks_are_isolated() -> None:
    engine = PersonFallRuleEngine(
        PersonFallRule(id="fall-1", zone=FULL_FRAME, fallen_confirmation_seconds=0.25)
    )
    engine.evaluate(
        [pose(1, posture="upright"), pose(2, posture="upright")],
        timestamp_seconds=0.0,
        frame_width=1000,
        frame_height=1000,
    )
    for timestamp in (0.25, 0.5, 0.75):
        matches = engine.evaluate(
            [pose(1, posture="down"), pose(2, posture="upright")],
            timestamp_seconds=timestamp,
            frame_width=1000,
            frame_height=1000,
        )
    assert [match.track_id for match in matches] == [1]
