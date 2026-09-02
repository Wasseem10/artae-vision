from video_intelligence_api.job_specs import SemanticVisionJob, ZoneEntryJob
from video_intelligence_api.visual_agent_plans import compile_visual_agent_plan


def test_deterministic_plan_uses_local_detection_and_tracking() -> None:
    plan = compile_visual_agent_plan(
        ZoneEntryJob(
            object_class="person",
            zone_id="zone-1",
            zone_name="entrance",
            minimum_confidence=0.25,
            absence_grace_seconds=1,
        ),
        "Alert me when a person enters the entrance",
    )
    assert plan.strategy == "deterministic_tracking"
    assert [node.executor for node in plan.nodes[1:3]] == [
        "YOLO + ByteTrack",
        "ByteTrack",
    ]


def test_semantic_plan_uses_vlm_and_keeps_actions_explicit() -> None:
    plan = compile_visual_agent_plan(
        SemanticVisionJob(
            instruction="Alert me when a masked person enters",
            object_class="person",
            zone_id="zone-1",
            zone_name="Full frame (automatic)",
            minimum_confidence=0.7,
            absence_grace_seconds=1,
            confirmation_windows=2,
            cooldown_seconds=30,
        ),
        "Alert me when a masked person enters",
    )
    assert plan.strategy == "semantic_window"
    ppe = next(
        node for node in plan.nodes if node.capability == "vision.skill.ppe_compliance"
    )
    assert ppe.executor == "Temporal VLM windows"
    assert ppe.depends_on == ["capture"]
    assert plan.nodes[-1].side_effect is True


def test_skill_router_selects_only_prompt_required_capabilities() -> None:
    plan = compile_visual_agent_plan(
        SemanticVisionJob(
            instruction="Alert when a treadmill screen shuts off",
            object_class="visual_event",
            zone_id="zone-1",
            zone_name="Full frame (automatic)",
        ),
        "Alert when a treadmill screen shuts off",
    )

    capabilities = {node.capability for node in plan.nodes}
    assert "vision.skill.ocr_text" in capabilities
    assert "vision.skill.open_grounding" in capabilities
    assert "vision.skill.change_anomaly" in capabilities
    assert "vision.skill.ppe_compliance" not in capabilities


def test_fall_plan_uses_continuous_local_pose_without_provider_requests() -> None:
    plan = compile_visual_agent_plan(
        SemanticVisionJob(
            instruction="Alert me if a worker falls to the ground",
            object_class="visual_event",
            zone_id="zone-1",
            zone_name="Full frame (automatic)",
            minimum_confidence=0.5,
        ),
        "Alert me if a worker falls to the ground",
    )

    assert plan.strategy == "specialized_pose"
    pose = next(
        node for node in plan.nodes if node.capability == "vision.skill.pose_action"
    )
    assert pose.executor == "Pose/action model"
    assert plan.nodes[-1].side_effect is True


def test_context_dependent_plan_is_explicitly_blocked() -> None:
    plan = compile_visual_agent_plan(
        SemanticVisionJob(
            instruction="Alert when an unauthorized person enters",
            zone_id="zone-1",
            zone_name="Full frame (automatic)",
        ),
        "Alert when an unauthorized person enters",
    )

    assert plan.support is not None
    assert plan.support.tier == "requires_context"
    assert plan.support.deployable is False
    assert "query.access_control" in {node.capability for node in plan.nodes}


def test_unobservable_intent_is_not_presented_as_a_camera_capability() -> None:
    plan = compile_visual_agent_plan(
        SemanticVisionJob(
            instruction="Alert when someone intends to steal",
            zone_id="zone-1",
            zone_name="Full frame (automatic)",
        ),
        "Alert when someone intends to steal",
    )

    assert plan.support is not None
    assert plan.support.tier == "not_visually_verifiable"
    assert plan.support.validation_required is False
    assert "reasoning.not_visually_observable" in {
        node.capability for node in plan.nodes
    }
    assert len(plan.nodes) == 2
    assert all(node.side_effect is False for node in plan.nodes)
