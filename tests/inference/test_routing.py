from dataclasses import replace

import pytest
from video_intelligence_inference.control_plane import ResolvedRuleConfig
from video_intelligence_inference.routing import route_rules
from video_intelligence_inference.zones import Point, Zone


def rule(
    rule_id: str,
    rule_type: str,
    strategy: str | None,
) -> ResolvedRuleConfig:
    return ResolvedRuleConfig(
        rule_id=rule_id,
        rule_type=rule_type,
        object_class="visual_event" if rule_type == "semantic_vision" else "person",
        minimum_confidence=0.7,
        absence_grace_seconds=1,
        geometry=Zone(
            "Full frame",
            (Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)),
        ),
        instruction="Evaluate the visible action"
        if rule_type == "semantic_vision"
        else None,
        execution_strategy=strategy,
    )


def test_router_builds_one_camera_plan_for_mixed_jobs() -> None:
    plan = route_rules(
        (
            rule("entry", "zone_entry", "deterministic_tracking"),
            rule("ppe", "semantic_vision", "semantic_window"),
        )
    )

    assert [item.rule_id for item in plan.deterministic_rules] == ["entry"]
    assert [item.rule_id for item in plan.semantic_rules] == ["ppe"]
    assert plan.needs_detector is True
    assert plan.needs_vision_provider is True


def test_router_skips_detector_for_semantic_only_camera() -> None:
    plan = route_rules((rule("screen-off", "semantic_vision", "semantic_window"),))

    assert plan.needs_detector is False
    assert plan.needs_vision_provider is True


def test_router_rejects_plan_that_changes_rule_semantics() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        route_rules((rule("unsafe", "zone_entry", "semantic_window"),))


def test_router_sends_fall_instruction_to_specialized_pose() -> None:
    fall = replace(
        rule("fall", "semantic_vision", "specialized_pose"),
        instruction="Alert me if a person falls to the ground",
    )

    plan = route_rules((fall,))

    assert [item.rule_id for item in plan.pose_rules] == ["fall"]
    assert plan.needs_pose_detector is True
    assert plan.needs_vision_provider is False
